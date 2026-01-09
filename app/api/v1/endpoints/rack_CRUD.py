from fastapi import APIRouter
from app.database.session import get_db
from app.database.models.user import User
from app.core import deps
from app.api.v1.schemas.rack import RackCreate
from app.database.models.rack import Rack
from sqlalchemy import select


router = APIRouter(prefix= "/racks", tags = ["Racks"])

@router.post("/")
async def create_rack(
    db: AsyncSession = Depends(get_db)
    admin: User = Depends(deps.get_current_admin)
    rack: RackCreate
): 
    newRack = Rack(**rack.dict())
    await db.add(newRack)
    await db.commit()
    await db.refresh(newRack)
    return {"message": "Rack created successfully"}


@router.patch("/")
async def update_rack(
    db: AsyncSession = Depends(get_db)
    admin: User = Depends(deps.get_current_admin)
    rack: RackUpdate
): 
    updatedRack = await db.get(Rack, rack.id)
    if not updatedRack:
        raise HTTPException(status_code=404, detail="Rack not found")


    if updatedRack:
        raise HTTPException(status_code=400, detail="Rack with this designation already exists")

    same_designation =db.execute(select(Rack).where(Rack.designation == rack.designation)).scalar_one_or_none()

    if same_designation:
        raise HTTPException(status_code=400, detail="Rack with this designation already exists")
    
    update_data = rack.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(updatedRack, key, value)

    await db.commit()
    await db.refresh(updatedRack)

    
    



    