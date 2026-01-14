from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.product_definition import ProductDefinitionIn
from app.database.models.product_definition import ProductDefinition
from pathlib import Path
from fastapi import File, HTTPException, UploadFile
from sqlalchemy import select
import os
import aiofiles
import uuid

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
            raise HTTPException(status_code=409, detail="Product definition with this barcode already exists")

        if product_definition.req_temp_min > product_definition.req_temp_max:
            raise HTTPException(status_code=400, detail="Required temperature min cannot be greater than required temperature max")

        if product_definition.dims_x_mm < 0 or product_definition.dims_y_mm < 0 or product_definition.dims_z_mm < 0:
            raise HTTPException(status_code=400, detail="Dimensions cannot be negative")

        if product_definition.expiry_days < 0:
            raise HTTPException(status_code=400, detail="Expiry days cannot be negative")

        if product_definition.weight_kg < 0:
            raise HTTPException(status_code=400, detail="Weight cannot be negative")
        
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
    async def upload_image(
        db: AsyncSession,
        product_definition_id: int,
        file: UploadFile,
    ) -> ProductDefinition:
        product_definition = await db.get(ProductDefinition, product_definition_id)
        if not product_definition:
            raise HTTPException(status_code=404, detail="Product definition not found")
        
        # 1. Define base upload directory
        # Using the standard path defined in Dockerfile/docker-compose
        upload_dir = Path("/app/media/product_images")
        
        # 2. Bezpieczne tworzenie folderu
        os.makedirs(upload_dir, exist_ok=True)
        
        # 3. Generowanie nazwy i ścieżki
        file_extension = os.path.splitext(file.filename)[1]
        if not file_extension:
            file_extension = ".jpg" # fallback
            
        new_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / new_filename
        
        # 4. Zapisywanie pliku z obsługą błędów
        try:
            async with aiofiles.open(str(file_path), 'wb') as out_file:
                # Reset kursora (na wypadek gdyby plik był czytany wcześniej)
                await file.seek(0)
                content = await file.read()
                await out_file.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save file: {str(e)}")
            
        # 5. Zapisujemy w DB ścieżkę relatywną (łatwiej potem serwować pliki)
        # Zapisujemy np: "product_images/unique_name.jpg"
        relative_path = os.path.join("product_images", new_filename)
        
        product_definition.photo_path = relative_path
        db.add(product_definition)
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
             raise HTTPException(status_code=404, detail="Product definition not found")
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
             raise HTTPException(status_code=404, detail="Product definition not found")
        
        # Delete image file if it exists
        if product_definition.photo_path:
            # photo_path is stored as "product_images/filename.jpg"
            # We need to prepend "/app/media/" to get full path
            # strip leading slash just in case to ensure it's treated as relative
            clean_rel_path = product_definition.photo_path.lstrip('/')
            full_path = Path("/app/media") / clean_rel_path
            
            print(f"Attempting to delete image at: {full_path}") # LOGGING
            
            if full_path.exists():
                try:
                    os.remove(full_path)
                    print(f"Successfully deleted photo: {full_path}")
                except OSError as e:
                    print(f"Error deleting file {full_path}: {e}")
            else:
                print(f"File not found at: {full_path}")

        await db.delete(product_definition)
        await db.commit()
        return {"message": "Product definition deleted successfully"}

    @staticmethod 
    async def proces_csv_import(file_content: bytes, db: AsyncSession):
        from app.schemas.product_definition import ProductDefinitionCSVRow, ImportResult 
        import csv 
        import io 

        try:
            content = file_content.decode("utf-8")
        except UnicodeDecodeError:
            return ImportResult(status="error", error="Invalid file encoding, must be UTF-8")
        
        rows: list[ProductDefinitionCSVRow] = []
        try:
            # Normalize newlines
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            
            clean_lines = []
            for line in lines:
                # If line is header (starts with #Nazwa), strip #
                # If line is comment (starts with # but not header), skip
                if line.startswith("#Nazwa"):
                    clean_lines.append(line.lstrip("#"))
                elif not line.startswith("#"):
                    clean_lines.append(line)
            
            reader = csv.DictReader(clean_lines, delimiter=";")
            
            for i, row_dict in enumerate(reader):
                # Filter out None keys if any (trailing semicolons)
                clean_row = {k: v for k, v in row_dict.items() if k and k.strip()}
                try:
                    # Treat empty strings as None? Pydantic expects correct types.
                    # bool conversion: "FALSE" -> False
                    # We rely on Pydantic's coercion, but "FALSE" string might need help if strict
                    # Check if manual conversion is needed for booleans
                    if "CzyNiebezpieczny" in clean_row:
                        val = clean_row["CzyNiebezpieczny"].upper()
                        if val == "TRUE": clean_row["CzyNiebezpieczny"] = True
                        elif val == "FALSE": clean_row["CzyNiebezpieczny"] = False
                        
                    validated_row = ProductDefinitionCSVRow.model_validate(clean_row)
                    rows.append(validated_row)
                except Exception as validation_error:
                    return ImportResult(
                        status="error", 
                        error=f"Validation failed at row {i+2} (data: {clean_row}): {str(validation_error)}"
                    )

        except Exception as e:
            return ImportResult(status="error", error=f"Failed to parse CSV structure: {str(e)}")
        
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
                     return ImportResult(
                        status="error", 
                        error=f"Duplicate barcode found in DB: {definition.barcode}"
                    )
                db.add(definition)
            
            await db.commit()
            return ImportResult(
                status="success", 
                message=f"Successfully imported {len(new_definitions)} product definitions."
            )
            
        except Exception as e:
            await db.rollback()
            return ImportResult(status="error", error=f"Database error during import: {str(e)}")
