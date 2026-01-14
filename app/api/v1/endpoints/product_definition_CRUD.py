
from app.database.session import get_db
from fastapi import APIRouter, File, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.product_definition import ProductDefinitionIn, ProductDefinitionOut
from app.database.models.product_definition import ProductDefinition
from app.core import deps
from app.services.product_definition_service import ProductDefinitionService 
from app.database.models.user import User
router = APIRouter();

@router.post("/", 
# response_model=ProductDefinitionOut
)
async def create_product_definition(
    product_definition: ProductDefinitionIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
    ):
    """
    Create a new product definition.

    Can only be executed by an admin user.
    """
    return await ProductDefinitionService.create_product_definition(
        db=db,
        product_definition=product_definition,
    )
    
@router.post("/{product_definition_id}/upload_image")
async def upload_image(
    product_definition_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
    file: UploadFile = File(...),
    ):
    """
    Upload an image for a product definition.

    Can only be executed by an admin user.
    """
    return await ProductDefinitionService.upload_image(
        db=db,
        product_definition_id=product_definition_id,
        file=file,
    )

@router.get("/{product_definition_id}", response_model=ProductDefinitionOut)
async def get_product_definition(
    product_definition_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin), # Allow read access to authenticated users or public? adhering to strict for now but easily changeable
):
    """
    Get a specific product definition by ID.
    """
    return await ProductDefinitionService.get_product_definition(
        db=db,
        product_definition_id=product_definition_id
    )

@router.get("/", response_model=list[ProductDefinitionOut])
async def get_product_definitions(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
):
    """
    Get all product definitions.
    """
    return await ProductDefinitionService.get_product_definitions(
        db=db,
        skip=skip,
        limit=limit
    )

@router.delete("/{product_definition_id}")
async def delete_product_definition(
    product_definition_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
):
    """
    Delete a product definition and its associated image.
    
    Can only be executed by an admin user.
    """
    return await ProductDefinitionService.delete_product_definition(
        db=db,
        product_definition_id=product_definition_id
    )