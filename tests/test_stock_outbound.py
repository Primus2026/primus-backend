from unittest.mock import AsyncMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, Rack, StockItem, ProductDefinition
from datetime import datetime, timedelta
from app.schemas.stock import RackLocation
from app.core import deps
from app.services.stock_service import StockService
from fastapi import HTTPException
from sqlalchemy import select

# Mock Redis
mock_redis = AsyncMock()

@pytest.mark.asyncio
async def test_initiate_success(
    db_session: AsyncSession,
):
    # Setup Data
    rack = Rack(
        designation="R-OUT-1",
        max_weight_kg=1000, max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=10, temp_max=20, rows_m=5, cols_n=5
    )
    db_session.add(rack)
    
    product = ProductDefinition(
        name="OutboundItem", barcode="OUT-123", expiry_days=30, weight_kg=1,
        req_temp_min=0, req_temp_max=100, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    await db_session.flush()

    user = User(login="unit_test_user", email="u@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    item = StockItem(
        rack_id=rack.id, product_id=product.id,
        entry_date=datetime.now(), expiry_date=datetime.now() + timedelta(days=30),
        position_row=1, position_col=1, received_by_id=user.id
    )
    db_session.add(item)
    await db_session.commit()

    # Call Service
    mock_redis.reset_mock()
    
    result = await StockService.outbound_stock_item_initiate(
        barcode="OUT-123", # Service takes barcode string directly
        db=db_session,
        user=user,
        redis_client=mock_redis
    )
    
    assert isinstance(result, RackLocation)
    assert result.designation == "R-OUT-1"
    
    # Verify Redis set called
    # Key: ExpectedChange:R-OUT-1:1:1
    expected_key = f"ExpectedChange:R-OUT-1:1:1"
    mock_redis.set.assert_called()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == expected_key
    assert args[1] == user.id 

@pytest.mark.asyncio
async def test_confirm_success(
    db_session: AsyncSession
):
    # Setup Data
    rack = Rack(
        designation="R-OUT-2",
        max_weight_kg=1000, max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=10, temp_max=20, rows_m=5, cols_n=5
    )
    db_session.add(rack)
    
    product = ProductDefinition(
        name="OutboundItem2", barcode="OUT-456", expiry_days=30, weight_kg=1,
        req_temp_min=0, req_temp_max=100, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    await db_session.flush()

    user = User(login="unit_test_user_2", email="u2@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    item = StockItem(
        rack_id=rack.id, product_id=product.id,
        entry_date=datetime.now(), expiry_date=datetime.now() + timedelta(days=30),
        position_row=2, position_col=2, received_by_id=user.id
    )
    db_session.add(item)
    await db_session.commit()

    # Mock Redis Get
    mock_redis.get.return_value = user.id 
    mock_redis.get.side_effect = None
    
    payload = RackLocation(
        designation="R-OUT-2",
        row=2,
        col=2
    )
    
    result = await StockService.outbound_stock_item_confirm(
        rack_location=payload,
        db=db_session,
        user=user,
        redis_client=mock_redis
    )

    assert result.message == "Stock item removed successfully"
    
    # Verify DB deletion
    result_db = await db_session.execute(select(StockItem).where(StockItem.id == item.id))
    assert result_db.scalar_one_or_none() is None
    
@pytest.mark.asyncio
async def test_cancel_success(
    db_session: AsyncSession
):
    user = User(login="unit_test_user_3", email="u3@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    mock_redis.get.return_value = user.id
    mock_redis.get.side_effect = None
    
    payload = RackLocation(
        designation="R-fake",
        row=9,
        col=9
    )
    
    result = await StockService.outbound_stock_item_cancel(
        rack_location=payload,
        user=user,
        redis_client=mock_redis
    )
    
    assert result.message == "Stock item outbound process cancelled successfully"
    mock_redis.delete.assert_called()

@pytest.mark.asyncio
async def test_outbound_fifo_entry_priority(
    db_session: AsyncSession
):
    # Setup Data
    rack = Rack(
        designation="R-FEFO-1",
        max_weight_kg=1000, max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=10, temp_max=20, rows_m=5, cols_n=5
    )
    db_session.add(rack)
    
    product = ProductDefinition(
        name="FEFO Item", barcode="FEFO-123", expiry_days=30, weight_kg=1,
        req_temp_min=0, req_temp_max=100, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    await db_session.flush()

    user = User(login="fefo_user", email="f@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Item A: Entered 5 days ago, Expires in 20 days (Older entry, later expiry)
    item_a = StockItem(
        rack_id=rack.id, product_id=product.id,
        entry_date=datetime.now() - timedelta(days=5), 
        expiry_date=datetime.now() + timedelta(days=20),
        position_row=1, position_col=1, received_by_id=user.id
    )
    
    # Item B: Entered 2 days ago, Expires in 5 days (Newer entry, sooner expiry)
    # This one should be picked because logic is FEFO (First Expired First Out)
    item_b = StockItem(
        rack_id=rack.id, product_id=product.id,
        entry_date=datetime.now() - timedelta(days=2), 
        expiry_date=datetime.now() + timedelta(days=5),
        position_row=1, position_col=2, received_by_id=user.id
    )
    
    db_session.add_all([item_a, item_b])
    await db_session.commit()

    # Call Service
    mock_redis.reset_mock()
    
    result = await StockService.outbound_stock_item_initiate(
        barcode="FEFO-123",
        db=db_session,
        user=user,
        redis_client=mock_redis
    )
    
    # Assert Item A (Col 1) is returned because it entered earlier (FIFO)
    assert isinstance(result, RackLocation)
    assert result.designation == "R-FEFO-1"
    assert result.col == 1 # Item A
    assert result.row == 1


@pytest.mark.asyncio
async def test_outbound_confirm_forbidden(
    db_session: AsyncSession
):
    # Setup Data
    rack = Rack(
        designation="R-AUTH-1",
        max_weight_kg=1000, max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=10, temp_max=20, rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.flush()

    # User A - Initiator
    user_a = User(id=100, login="user_a", email="a@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    # User B - Intruder
    user_b = User(id=101, login="user_b", email="b@t.pl", password_hash="hash", role="WAREHOUSEMAN", is_active=True)
    
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    # Mock Redis: Stored value is User A's ID
    mock_redis.get.return_value = str(user_a.id)
    mock_redis.get.side_effect = None
    
    payload = RackLocation(
        designation="R-AUTH-1",
        row=1,
        col=1
    )
    
    # Attempt confirm with User B
    with pytest.raises(HTTPException) as excinfo:
        await StockService.outbound_stock_item_confirm(
            rack_location=payload,
            db=db_session,
            user=user_b,
            redis_client=mock_redis
        )
    
    assert excinfo.value.detail == "You are not authorized to confirm this outbound process"

@pytest.mark.asyncio
async def test_initiate_not_found(
    db_session: AsyncSession
):
    """Test 404 when no stock items exist"""
    # Create product but no items
    product = ProductDefinition(
        name="Empty Product", barcode="EMPTY-123", expiry_days=30, weight_kg=1,
        req_temp_min=0, req_temp_max=100, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    await db_session.commit()
    
    user = User(login="u_empty", email="e@t.pl", password_hash="x", role="WAREHOUSEMAN", is_active=True)
    db_session.add(user)
    await db_session.commit()
    
    with pytest.raises(HTTPException) as excinfo:
        await StockService.outbound_stock_item_initiate(
            barcode="EMPTY-123",
            db=db_session,
            user=user,
            redis_client=mock_redis
        )
    
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Stock item not found"
