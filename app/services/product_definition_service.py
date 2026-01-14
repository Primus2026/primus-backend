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