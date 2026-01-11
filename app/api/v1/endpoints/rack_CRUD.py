from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.database.models.user import User
from app.core import deps
from app.api.v1.schemas.rack import RackCreate, RackUpdate, RackOut
from app.schemas.csv_import import ImportResult
from app.services.rack_service import RackService

router = APIRouter(prefix="/racks", tags=["Racks"])

@router.post("/", response_model=RackOut)
async def create_rack(
    rack: RackCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
): 
    """
    Create a new rack.
    
    Can only be executed by an admin user.
    """
    return await RackService.create_rack(db, rack)

@router.post("/import", response_model=ImportResult, responses={
    400: {"description": "Validation failed (e.g. invalid CSV, encoding error, or too many conflicts)"},
    403: {"description": "Not enough permissions (Admin required)"}
})
async def import_racks(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
):
    """
    Import racks configuration from a CSV file.
    
    The CSV file should contain rack definitions. The import process will:
    - Validate the CSV format and content.
    - Check for conflicts with existing stock items (e.g., if new rack definition is smaller than existing items).
    - Create new racks or update existing ones.
    
    Returns a summary of the import result.
    """
    content = await file.read()
    return await RackService.process_csv_import(content, db)

@router.patch("/", response_model=RackOut, responses={
    404: {"description": "Rack not found"},
    400: {"description": "Rack with this designation already exists"}
})
async def update_rack(
    rack: RackUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
): 
    """
    Update an existing rack.
    
    Can only be executed by an admin user.
    """
    return await RackService.update_rack(db, rack)

@router.delete("/{rack_id}", responses={
    404: {"description": "Rack not found"},
    400: {"description": "Rack is not empty"}
})
async def delete_rack(
    rack_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
): 
    """
    Delete a rack.
    
    Can only be executed by an admin user.
    Will fail if the rack is not empty (contains stock items).
    """
    await RackService.delete_rack(db, rack_id)
    return {"message": "Rack deleted successfully"}

@router.get("/{rack_id}", response_model=RackOut, responses={
    404: {"description": "Rack not found"}
})
async def get_rack(
    rack_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
): 
    """
    Get rack details by ID.
    
    Can only be executed by an admin user.
    """
    return await RackService.get_rack(db, rack_id)