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
    Utworzenie nowego regału.
    
    Wymaga uprawnień administratora.
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
    Import regałów z pliku CSV.
    
    Plik CSV powinien zawierać definicje regałów. Proces:
    - Walidacja formatu i zawartości.
    - Sprawdzenie konfliktów z istniejącymi towarami.
    - Tworzenie lub aktualizacja regałów.
    
    Proces jest asynchroniczny (Celery). Wynik można sprawdzić endpointem GET /import/{task_id}.
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
    Pobranie wyniku procesu importu.
    
    Służy do odpytywania (polling) o status zadania importu zainicjowanego przez POST /import.
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
    Pobranie wszystkich regałów wraz z aktualnym stanem magazynowym (sloty, wagi).
    Używane przez MQTT Listener do inicjalizacji cache.
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
    Pobranie listy towarów składowanych na konkretnym regale.
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
    Aktualizacja istniejącego regału.
    
    Wymaga uprawnień administratora.
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
    Usunięcie regału.
    
    Wymaga uprawnień administratora.
    Operacja nie powiedzie się, jeśli regał nie jest pusty.
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
    Pobranie szczegółów regału po ID.
    """
    return await RackService.get_rack(db, rack_id)


@router.get("/", response_model=list[RackOut])
async def get_all_racks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
): 
    """
    Pobranie listy wszystkich regałów.
    """
    return await RackService.get_all_racks(db)