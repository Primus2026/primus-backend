from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.product_definition import ProductDefinitionIn, ProductDefinitionUpdate
from app.database.models.product_definition import ProductDefinition
from app.database.models.stock_item import StockItem
from app.database.models.product_stats import ProductStats
from pathlib import Path
from fastapi import File, HTTPException, UploadFile
from sqlalchemy import select, delete
import os
import aiofiles
import uuid
from app.core.config import settings
from app.core.storage import storage

class ProductDefinitionService:
    @staticmethod 
    async def validate_product_definition(
        product_definition: ProductDefinitionIn,
        db: AsyncSession,
    ):
        result = await db.execute(
            select(ProductDefinition)
            .where(ProductDefinition.barcode == product_definition.barcode)
        )

        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Produkt z tym kodem kreskowym już istnieje")

        if product_definition.req_temp_min > product_definition.req_temp_max:
            raise HTTPException(status_code=400, detail="Minimalna temperatura wymagana nie może być wyższa niż maksymalna temperatura wymagana")

        if product_definition.dims_x_mm < 0 or product_definition.dims_y_mm < 0 or product_definition.dims_z_mm < 0:
            raise HTTPException(status_code=400, detail="Wymiary nie mogą być ujemne")

        if product_definition.expiry_days < 0:
            raise HTTPException(status_code=400, detail="Data ważności nie może być ujemna")

        if product_definition.weight_kg < 0:
            raise HTTPException(status_code=400, detail="Waga nie może być ujemna")
        
    @staticmethod 
    async def create_product_definition(
        db: AsyncSession,
        product_definition: ProductDefinitionIn,
    ) -> ProductDefinition:
        await ProductDefinitionService.validate_product_definition(
            product_definition=product_definition,
            db=db
            )
        
        new_product_definition = ProductDefinition(
            **product_definition.dict()
        )
        db.add(new_product_definition)
        await db.commit()
        await db.refresh(new_product_definition)
        return new_product_definition

    @staticmethod
    async def update_product_definition(
        db: AsyncSession,
        product_definition_id: int,
        product_update: "ProductDefinitionUpdate",
    ) -> ProductDefinition:
        product = await db.get(ProductDefinition, product_definition_id)
        if not product:
            raise HTTPException(status_code=404, detail="Nie znaleziono definicji produktu")

        update_data = product_update.dict(exclude_unset=True)
        
        # Validate if barcode is being changed to one that exists
        if "barcode" in update_data and update_data["barcode"] != product.barcode:
             existing = await db.execute(
                select(ProductDefinition)
                .where(ProductDefinition.barcode == update_data["barcode"])
            )
             if existing.scalar_one_or_none():
                 raise HTTPException(status_code=409, detail="Produkt z tym kodem kreskowym już istnieje")

        # Validate logic if temps are changed
        req_min = update_data.get("req_temp_min", product.req_temp_min)
        req_max = update_data.get("req_temp_max", product.req_temp_max)
        if req_min > req_max:
             raise HTTPException(status_code=400, detail="Minimalna temperatura wymagana nie może być wyższa niż maksymalna temperatura wymagana")

        for key, value in update_data.items():
            setattr(product, key, value)

        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product
    
    @staticmethod 
    async def upload_image(
        db: AsyncSession,
        product_definition_id: int,
        file: UploadFile,
    ) -> ProductDefinition:
        product_definition = await db.get(ProductDefinition, product_definition_id)
        if not product_definition:
            raise HTTPException(status_code=404, detail="Nie znaleziono definicji produktu")
        
        # 1. Generate filename and path
        file_extension = os.path.splitext(file.filename)[1]
        if not file_extension:
            file_extension = ".jpg" # fallback
            
        new_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Store as: product_images/UUID.jpg
        relative_path = f"product-images/{new_filename}" 
        
        # 2. Save file using storage provider
        try:
            await storage.save(relative_path, file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Nie udało się zapisać pliku: {str(e)}")
            
        # 3. Update DB
        
        product_definition.photo_path = relative_path
        db.add(product_definition)
        await db.commit()
        await db.refresh(product_definition)
        
        return product_definition

    @staticmethod
    async def upload_image_from_path(
        db: AsyncSession,
        product_definition: ProductDefinition,
        local_file_path: Path
    ) -> ProductDefinition:
        """
        Moves a file from a local temporary path to the final destination 
        and updates the product definition.
        """
        file_extension = os.path.splitext(local_file_path.name)[1]
        if not file_extension:
            file_extension = ".jpg" 
        
        new_filename = f"{uuid.uuid4()}{file_extension}"
        relative_path = f"product-images/{new_filename}"
        
        try:
            # Read local file and upload
            async with aiofiles.open(local_file_path, 'rb') as f:
                content = await f.read()
                await storage.save(relative_path, content)
            
            # Clean up local file because this function implies a "move" or consumption of temp file
            os.remove(local_file_path)

        except Exception as e:
            raise Exception(f"Failed to upload file {local_file_path} to storage: {e}")
        product_definition.photo_path = relative_path
        db.add(product_definition)
        # Commit should be handled by caller usually for bulk invoke, 
        # but here we might want to commit per item to save progress. 
        # The prompt asked for "Collect results", so per-item commit is safer against one failure blocking all.
        await db.commit()
        await db.refresh(product_definition)
        return product_definition

    @staticmethod
    async def get_product_definition(
        db: AsyncSession,
        product_definition_id: int
    ) -> ProductDefinition:
        result = await db.get(ProductDefinition, product_definition_id)
        if not result:
             raise HTTPException(status_code=404, detail="Nie znaleziono definicji produktu")
        return result

    @staticmethod
    async def get_product_definitions(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> list[ProductDefinition]:
        result = await db.execute(
            select(ProductDefinition).offset(skip).limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def delete_product_definition(
        db: AsyncSession,
        product_definition_id: int
    ):
        product_definition = await db.get(ProductDefinition, product_definition_id)
        if not product_definition:
             raise HTTPException(status_code=404, detail="Nie znaleziono definicji produktu")
        
        # Check if there are any stock items for this product
        stock_result = await db.execute(
            select(StockItem).where(StockItem.product_id == product_definition_id)
        )
        if stock_result.first():
            raise HTTPException(
                status_code=409, 
                detail="Nie można usunąć produktu, ponieważ istnieją powiązane z nim pozycje w magazynie."
            )
        # Delete image file if it exists
        if product_definition.photo_path:
            # photo_path is stored as "product_images/filename.jpg"
            clean_rel_path = product_definition.photo_path.lstrip('/')
            
            print(f"Attempting to delete image at: {clean_rel_path}") # LOGGING
            
            # It's safer to just try delete and ignore errors if not found
            try:
                await storage.delete(clean_rel_path)
                print(f"Successfully deleted photo: {clean_rel_path}")
            except Exception as e:
                 print(f"Error deleting file {clean_rel_path}: {e}")

        # Delete related product stats
        await db.execute(
            delete(ProductStats).where(ProductStats.product_id == product_definition_id)
        )

        await db.delete(product_definition)
        await db.commit()
        return {"message": "Produkt usunięty pomyślnie"}

    @staticmethod 
    async def proces_csv_import(file_content: bytes, db: AsyncSession):
        from app.schemas.product_definition import ProductDefinitionCSVRow, ProductImportResult 
        import csv 
        import io 

        try:
            # Use utf-8-sig to handle BOM if present
            content = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Fallback to utf-8 if sig fails (though utf-8-sig handles no BOM too)
            try:
                content = file_content.decode("utf-8")
            except UnicodeDecodeError:
                return ProductImportResult(status="error", error="Invalid file encoding, must be UTF-8")
        
        rows: list[ProductDefinitionCSVRow] = []
        try:
            # Normalize newlines
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            
            clean_lines = []
            header_found = False
            
            for line in lines:
                # 1. Skip comments that are NOT part of the header block
                if line.startswith("#") and "Nazwa" not in line:
                    continue
                
                # 2. Identify Header Line
                # We look for "Nazwa" because it's the first required column alias
                if not header_found:
                    if "Nazwa" in line:
                        # Found header!
                        header_found = True
                        clean_lines.append(line.lstrip("#")) # Remove comment char if present in header
                    else:
                        # Skip garbage lines before header
                        continue
                else:
                    # 3. Process Data Lines
                    if not line.startswith("#"):
                        clean_lines.append(line)
            
            if not clean_lines:
                 return ProductImportResult(status="error", error="Nie znaleziono poprawnego nagłówka CSV (musi zawierać 'Nazwa')")

            reader = csv.DictReader(clean_lines, delimiter=";")
            
            for i, row_dict in enumerate(reader):
                # Filter out None keys if any (trailing semicolons)
                clean_row = {k: v for k, v in row_dict.items() if k and k.strip()}
                try:
                    if "CzyNiebezpieczny" in clean_row:
                        val = clean_row["CzyNiebezpieczny"].upper()
                        if val == "TRUE": clean_row["CzyNiebezpieczny"] = True
                        elif val == "FALSE": clean_row["CzyNiebezpieczny"] = False
                        
                    validated_row = ProductDefinitionCSVRow.model_validate(clean_row)
                    rows.append(validated_row)
                except Exception as validation_error:
                    return ProductImportResult(
                        status="error", 
                        error=f"Validation failed at row {i+2} (data: {clean_row}): {str(validation_error)}"
                    )

        except Exception as e:
            return ProductImportResult(status="error", error=f"Failed to parse CSV structure: {str(e)}")
        
        # If we got here, all rows are valid according to Pydantic
        # Now check for business logic conflicts (e.g. barcode uniqueness)
        
        new_definitions = []
        for row in rows:
            # Map CSV Row to DB Model
            product_data = row.dict(by_alias=False)
            new_def = ProductDefinition(**product_data)
            new_definitions.append(new_def)

        try:
            for definition in new_definitions:
                # Check if exists to avoid generic IntegrityError - optional but safer
                existing = await db.execute(
                    select(ProductDefinition).where(ProductDefinition.barcode == definition.barcode)
                )
                if existing.scalar_one_or_none():
                     return ProductImportResult(
                        status="error", 
                        error=f"Duplicate barcode found in DB: {definition.barcode}"
                    )
                db.add(definition)
            
            await db.commit()
            
            # Construct summary
            summary = {
                "total_processed": len(rows),
                "created_count": len(new_definitions),
                "updated_count": 0,
                "skipped_count": 0,
                "skipped_details": [],
                "success_count": len(new_definitions), # Backend schema uses success_count
                "error_count": 0,
                "errors": [],
                "successes": []
            }
            
            return ProductImportResult(
                status="completed", 
                message=f"Successfully imported {len(new_definitions)} product definitions.",
                summary=summary
            )
            
        except Exception as e:
            await db.rollback()
            return ProductImportResult(status="error", error=f"Database error during import: {str(e)}")
