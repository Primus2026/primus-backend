from unittest.mock import AsyncMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, Rack, StockItem, ProductDefinition
from app.database.models.product_definition import FrequencyClass
from app.services.allocation_service import AllocationService
from app.schemas.stock import RackLocation
from fastapi import HTTPException
from sqlalchemy import select
import json
from datetime import datetime

# Mock Redis
mock_redis = AsyncMock()

@pytest.fixture
def clean_redis():
    mock_redis.reset_mock()
    return mock_redis

@pytest.mark.asyncio
async def test_allocate_item_success_class_a(db_session: AsyncSession, clean_redis):
    """Test allocation for Class A product (Closest to exit)"""
    # Setup Data
    # Rack 1: Far (20m)
    rack1 = Rack(
        designation="R-A-1", max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=5, temp_max=15, rows_m=2, cols_n=2, distance_from_exit_m=20
    )
    # Rack 2: Close (5m) -> Should be picked
    rack2 = Rack(
        designation="R-A-2", max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=5, temp_max=15, rows_m=2, cols_n=2, distance_from_exit_m=5
    )
    db_session.add_all([rack1, rack2])
    
    product = ProductDefinition(
        name="Prod A", barcode="A-111", expiry_days=30, weight_kg=1,
        req_temp_min=5, req_temp_max=15, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10,
        frequency_class=FrequencyClass.A
    )
    db_session.add(product)
    await db_session.commit()

    user = User(login="alloc_user", email="al@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()

    # Mock Redis: ensure exists returns False (slot empty)
    clean_redis.exists.return_value = False

    # Execute
    result = await AllocationService.allocate_item(
        db=db_session,
        barcode="A-111",
        user=user,
        redis_client=clean_redis
    )

    # Assert
    assert result.rack_designation == "R-A-2"
    assert result.row == 1
    assert result.col == 1
    
    # Verify Redis Lock
    expected_key = f"ExpectedChange:R-A-2:1:1"
    clean_redis.set.assert_called()
    args, _ = clean_redis.set.call_args
    assert args[0] == expected_key
    assert json.loads(args[1])["user_id"] == user.id

@pytest.mark.asyncio
async def test_allocate_item_success_class_c(db_session: AsyncSession, clean_redis):
    """Test allocation for Class C product (Farthest from exit)"""
    # Rack 1: Far (20m) -> Should be picked
    rack1 = Rack(
        designation="R-C-1", max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=5, temp_max=15, rows_m=2, cols_n=2, distance_from_exit_m=20
    )
    # Rack 2: Close (5m)
    rack2 = Rack(
        designation="R-C-2", max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=5, temp_max=15, rows_m=2, cols_n=2, distance_from_exit_m=5
    )
    db_session.add_all([rack1, rack2])
    
    product = ProductDefinition(
        name="Prod C", barcode="C-333", expiry_days=30, weight_kg=1,
        req_temp_min=5, req_temp_max=15, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10,
        frequency_class=FrequencyClass.C
    )
    db_session.add(product)
    await db_session.commit()
    
    user = User(login="alloc_user_c", email="c@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    clean_redis.exists.return_value = False

    result = await AllocationService.allocate_item(
        db=db_session,
        barcode="C-333",
        user=user,
        redis_client=clean_redis
    )

    assert result.rack_designation == "R-C-1"

@pytest.mark.asyncio
async def test_allocate_item_no_suitable_racks_requirements(db_session: AsyncSession, clean_redis):
    """Test failure when no racks meet physical requirements"""
    # Rack doesn't meet temp reqs
    rack = Rack(
        designation="R-FAIL", max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=0, temp_max=5, # Too cold
        rows_m=2, cols_n=2
    )
    db_session.add(rack)
    
    product = ProductDefinition(
        name="Hot Item", barcode="H-999", expiry_days=30, weight_kg=1,
        req_temp_min=20, req_temp_max=30, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10,
        frequency_class=FrequencyClass.A
    )
    db_session.add(product)
    await db_session.commit()
    
    user = User(login="fail_user", email="f@t.pl", password_hash="hash")

    with pytest.raises(HTTPException) as excinfo:
        await AllocationService.allocate_item(db_session, "H-999", user, clean_redis)
    
    assert excinfo.value.status_code == 400
    assert "Nie znaleziono regałów spełniających wymagań fizycznych" in excinfo.value.detail

@pytest.mark.asyncio
async def test_allocate_item_no_slots(db_session: AsyncSession, clean_redis):
    """Test failure when valid racks are full"""
    rack = Rack(
        designation="R-FULL", max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=5, temp_max=15, rows_m=1, cols_n=1 # 1 slot total
    )
    db_session.add(rack)
    await db_session.flush()
    
    product = ProductDefinition(
        name="Prod Full", barcode="F-000", expiry_days=30, weight_kg=1,
        req_temp_min=5, req_temp_max=15, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    
    user = User(login="full_user", email="fu@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()

    # Fill the only slot
    item = StockItem(
        rack_id=rack.id, product_id=product.id, position_row=1, position_col=1,
        received_by_id=user.id, entry_date=datetime.now(), expiry_date=datetime.now()
    )
    db_session.add(item)
    await db_session.commit()

    clean_redis.exists.return_value = False # Redis says free, but DB says occupied

    with pytest.raises(HTTPException) as excinfo:
        await AllocationService.allocate_item(db_session, "F-000", user, clean_redis)
        
    assert excinfo.value.status_code == 400
    assert "Nie znaleziono wolnego miejsca" in excinfo.value.detail

@pytest.mark.asyncio
async def test_confirm_allocation_success(db_session: AsyncSession, clean_redis):
    """Test successful confirmation of allocation"""
    rack = Rack(
        designation="R-CONF", max_weight_kg=1000, max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=0, temp_max=20, rows_m=5, cols_n=5
    )
    db_session.add(rack)
    
    product = ProductDefinition(
        name="Conf Prod", barcode="CONF-1", expiry_days=10, weight_kg=5.0,
        req_temp_min=0, req_temp_max=20, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    await db_session.commit()
    
    user = User(login="conf_user", email="c@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()
    
    # Setup Redis Lock
    lock_data = json.dumps({"user_id": user.id, "product_id": product.id})
    clean_redis.get.return_value = lock_data
    
    payload = RackLocation(designation="R-CONF", row=1, col=1)
    
    result = await AllocationService.confirm_allocation(
        rack_location=payload,
        user=user,
        redis_client=clean_redis,
        db=db_session
    )
    
    assert result.rack_id == rack.id
    assert result.position_row == 1
    assert result.position_col == 1
    
    # Verify DB insertion
    db_item = await db_session.scalar(select(StockItem).where(StockItem.rack_id == rack.id))
    assert db_item is not None
    assert db_item.product_id == product.id
    
    # Verify Weight Update check
    # We can check if hincrby was called
    clean_redis.hincrby.assert_called_with(f"Rack:R-CONF", "weight_kg", 5)

@pytest.mark.asyncio
async def test_confirm_allocation_unauthorized(db_session: AsyncSession, clean_redis):
    """Test confirmation failure when user doesn't match lock"""
    user_owner = User(id=999, login="owner", email="o@t.pl", password_hash="x", role="WAREHOUSEMAN", is_active=True)
    user_intruder = User(id=666, login="intruder", email="i@t.pl", password_hash="x", role="WAREHOUSEMAN", is_active=True)
    
    lock_data = json.dumps({"user_id": user_owner.id, "product_id": 1})
    clean_redis.get.return_value = lock_data
    
    payload = RackLocation(designation="R-X", row=1, col=1)
    
    with pytest.raises(HTTPException) as excinfo:
        await AllocationService.confirm_allocation(payload, user_intruder, clean_redis, db_session)
        
    assert excinfo.value.status_code == 400
    assert "nie jest zablokowana dla tego użytkownika" in excinfo.value.detail

@pytest.mark.asyncio
async def test_cancel_allocation_success(db_session: AsyncSession, clean_redis):
    """Test successful cancellation"""
    user = User(id=123, login="u", email="u@t.pl", password_hash="x")
    
    lock_data = json.dumps({"user_id": user.id, "product_id": 1})
    clean_redis.get.return_value = lock_data
    
    payload = RackLocation(designation="R-CANC", row=1, col=1)
    
    await AllocationService.cancel_allocation(payload, user, clean_redis)
    
    # Verify lock deletion
    clean_redis.delete.assert_called_with(f"ExpectedChange:R-CANC:1:1")
