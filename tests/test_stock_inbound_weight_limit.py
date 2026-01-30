import pytest
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, Rack, StockItem, ProductDefinition
from app.database.models.product_definition import FrequencyClass
from app.services.allocation_service import AllocationService
from fastapi import HTTPException
from datetime import datetime

# Fixture for clean redis specific to this test file if needed, 
# but we can use the one from conftest or mock it locally.
# existing test_stock_inbound.py used:
@pytest.fixture
def clean_redis():
    mock = AsyncMock()
    mock.exists.return_value = False
    mock.get.return_value = None
    mock.set.return_value = True
    return mock

@pytest.mark.asyncio
async def test_allocate_item_weight_limit_total(db_session: AsyncSession, clean_redis):
    """
    Test that allocation checks TOTAL weight (existing + new) <= max_weight.
    """
    # 1. Setup Rack
    # Max weight 100kg.
    rack = Rack(
        designation="R-WEIGHT-TEST", 
        max_weight_kg=100.0, 
        max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=0, temp_max=20, 
        rows_m=5, cols_n=5,
        distance_from_exit_m=10
    )
    db_session.add(rack)
    await db_session.flush()

    # 2. Setup Existing Item (95kg)
    prod_heavy = ProductDefinition(
        name="Heavy Item", barcode="HEAVY-1", expiry_days=30, weight_kg=95.0,
        req_temp_min=0, req_temp_max=20, dims_x_mm=100, dims_y_mm=100, dims_z_mm=100
    )
    db_session.add(prod_heavy)
    await db_session.flush()

    user = User(login="w_user", email="w@t.pl", password_hash="x", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.flush()

    item_existing = StockItem(
        rack_id=rack.id, product_id=prod_heavy.id, position_row=1, position_col=1,
        received_by_id=user.id, entry_date=datetime.now(), expiry_date=datetime.now()
    )
    db_session.add(item_existing)
    await db_session.commit()

    # 3. Try to allocate New Item (6kg) -> Tuple 95+6=101 > 100. Should Fail.
    prod_fail = ProductDefinition(
        name="Fail Item", barcode="FAIL-6KG", expiry_days=30, weight_kg=6.0,
        req_temp_min=0, req_temp_max=20, dims_x_mm=100, dims_y_mm=100, dims_z_mm=100,
        frequency_class=FrequencyClass.A
    )
    db_session.add(prod_fail)
    await db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        await AllocationService.allocate_item(db_session, "FAIL-6KG", user, clean_redis)
    
    # It should say "No suitable racks found" or similar
    assert excinfo.value.status_code == 400
    # Our new message is "No suitable racks found (weight limit reached)" 
    # OR "No suitable racks found meeting physical requirements" if pre-filter fails (it shouldn't, 6 < 100)
    # The message comes from the second check: "No suitable racks found (weight limit reached)"
    assert "weight limit reached" in excinfo.value.detail or "No suitable racks found" in excinfo.value.detail

    # 4. Try to allocate New Item (4kg) -> Tuple 95+4=99 <= 100. Should Success.
    prod_pass = ProductDefinition(
        name="Pass Item", barcode="PASS-4KG", expiry_days=30, weight_kg=4.0,
        req_temp_min=0, req_temp_max=20, dims_x_mm=100, dims_y_mm=100, dims_z_mm=100,
         frequency_class=FrequencyClass.A
    )
    db_session.add(prod_pass)
    await db_session.commit()

    result = await AllocationService.allocate_item(db_session, "PASS-4KG", user, clean_redis)
    assert result.rack_designation == "R-WEIGHT-TEST"
