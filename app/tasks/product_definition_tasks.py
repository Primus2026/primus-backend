import asyncio
from app.core.celery_worker import celery_app
from app.services.product_definition_service import ProductDefinitionService
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

async def process_import_async(file_content: bytes):
    # Create a local engine/session for this specific asyncio loop
    # This prevents "Future attached to a different loop" errors in Celery
    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        try:
            return await ProductDefinitionService.proces_csv_import(file_content, session)
        finally:
            await engine.dispose()

@celery_app.task(name="product_definition_tasks.import_product_definitions")    
def import_product_definitions(file_content: bytes):
    result = asyncio.run(process_import_async(file_content))
    return result.model_dump()

async def process_bulk_upload_async(temp_dir: str):
    import os
    from pathlib import Path
    import shutil
    from sqlalchemy import select
    from app.database.models.product_definition import ProductDefinition

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    results = {
        "total_processed": 0,
        "success_count": 0,
        "error_count": 0,
        "errors": [],
        "successes": []
    }
    
    temp_path = Path(temp_dir)
    
    try:
        if not temp_path.exists():
            return {
                "total_processed": 0,
                "success_count": 0,
                "error_count": 1,
                "errors": [f"Temp directory not found: {temp_dir}"],
                "successes": []
            }

        files = [f for f in temp_path.iterdir() if f.is_file()]
        results["total_processed"] = len(files)
        
        async with AsyncSessionLocal() as session:
            for file_path in files:
                filename = file_path.name
                try:
                    # Search for product definition where photo_path matches filename
                    # We assume the CSV import populated photo_path with the filename
                    query = select(ProductDefinition).where(ProductDefinition.photo_path == filename)
                    result = await session.execute(query)
                    product_def = result.scalars().first()
                    
                    if product_def:
                        updated_product = await ProductDefinitionService.upload_image_from_path(
                            db=session,
                            product_definition=product_def,
                            local_file_path=file_path
                        )
                        results["success_count"] += 1
                        results["successes"].append({
                            "original_filename": filename,
                            "new_path": updated_product.photo_path,
                            "product_id": updated_product.id
                        })
                    else:
                        results["error_count"] += 1
                        results["errors"].append(f"No match for {filename}")
                
                except Exception as e:
                    results["error_count"] += 1
                    results["errors"].append(f"Error processing {filename}: {str(e)}")

    finally:
        # Cleanup temp directory
        if temp_path.exists():
            shutil.rmtree(temp_path)
        await engine.dispose()
        
    return results

@celery_app.task(name="product_definition_tasks.bulk_upload_images")
def bulk_upload_images(temp_dir: str):
    return asyncio.run(process_bulk_upload_async(temp_dir))
