from fastapi import APIRouter, Depends, UploadFile, File, Path, HTTPException  
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.database.models.user import User
from app.core import deps
from app.schemas.rack import RackCreate, RackUpdate, RackOut, RackImportResult, RackWithInventory
from app.schemas.stock import StockOut
from app.services.rack_service import RackService
from app.core.celery_worker import celery_app
from app.tasks.csv_import import import_racks as import_racks_task

router = APIRouter()

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

@router.post("/import", response_model=RackImportResult, responses={
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

    The import process is executed asynchronously using Celery.
    The result of the import process can be checked using the GET method on the /import/{celery_task_id} endpoint.
    """
    content = await file.read()
    task = import_racks_task.delay(content)
    
    return RackImportResult(
        message="Import started successfully", 
        status="processing",
        task_id=task.id
    )


@router.get("/import/{celery_task_id}", response_model=RackImportResult, responses={
    403: {"description": "Not enough permissions (Admin required)"},
    404: {"description": "Import task not found"},
})
async def get_import_result(
    celery_task_id: str = Path(...),
    admin: User = Depends(deps.get_current_admin),
):
    """
    Get the result of the import process.

    Example use would be fetching every second to check status of the import process.
    The task_id is returned after requesting an import with the POST method on the /import endpoint.
    """
    
    try:
        task = celery_app.AsyncResult(celery_task_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail="Import task not found")

    

    if task.state == 'PENDING':
        return RackImportResult(status="processing", task_id=celery_task_id)
    
    elif task.state == 'FAILURE':
        return RackImportResult(status="failed", error=str(task.result), task_id=celery_task_id)
        

    #Task already returns a pydantic model, you have to overwrite dict fields
    elif task.state == 'SUCCESS':
        result_data = task.result
        if isinstance(result_data, dict):
            result_data["status"] = "completed"
            result_data["task_id"] = celery_task_id
        return RackImportResult(**result_data)
    


@router.get("/inventory-state", response_model=list[RackWithInventory])
async def get_racks_inventory_state(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get all racks with current inventory state (active slots and weights).
    Used by MQTT Listener to initialize cache to prevent cold start false alerts.
    """
    return await RackService.get_racks_with_inventory(db)


@router.get("/{rack_id}/stock-items", response_model=list[StockOut], responses={
    404: {"description": "Rack not found"}
})
async def get_rack_stock_items(
    rack_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
): 
    """
    Get all stock items for a specific rack.
    
    Can be executed by any authenticated user.
    """
    return await RackService.get_rack_stock_items(db, rack_id)


@router.put("/{rack_id}", response_model=RackOut, responses={
    404: {"description": "Rack not found"},
    400: {"description": "Rack with this designation already exists"}
})
async def update_rack(
    rack: RackUpdate,
    rack_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
): 
    """
    Update an existing rack.
    
    Can only be executed by an admin user.
    """
    return await RackService.update_rack(db, rack_id, rack)

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
    rack_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
): 
    """
    Get rack details by ID.
    
    Can be executed by any authenticated user.
    """
    return await RackService.get_rack(db, rack_id)


@router.get("/", response_model=list[RackOut])
async def get_all_racks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
): 
    """
    Get all racks.
    
    Can be executed by any authenticated user.
    """
    return await RackService.get_all_racks(db)