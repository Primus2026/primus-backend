import pytest
from datetime import date, datetime
from app.models.product_definition import ProductDefinition
from app.models.stock_item import StockItem
from app.models.rack import Rack
from app.models.user import User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

@pytest.mark.asyncio
async def test_create_product_definition(db_session: AsyncSession):
    product = ProductDefinition(
        name="Test Product",
        barcode="123456789",
        req_temp_min=20.0,
        req_temp_max=25.0,
        weight_kg=1.5,
        dims_x_mm=100,
        dims_y_mm=100,
        dims_z_mm=100,
        expiry_days=30
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    assert product.id is not None
    assert product.name == "Test Product"

@pytest.mark.asyncio
async def test_create_stock_item_relationship(db_session: AsyncSession):
    # 1. Create Dependencies
    product = ProductDefinition(
        name="Stock Product",
        barcode="987654321",
        req_temp_min=0.0,
        req_temp_max=10.0,
        weight_kg=1.0,
        dims_x_mm=50,
        dims_y_mm=50,
        dims_z_mm=50,
        expiry_days=60
    )
    
    rack = Rack(
        designation="A-01",
        rows_m=5,
        cols_n=10,
        temp_min=0.0,
        temp_max=10.0,
        max_weight_kg=100.0,
        max_dims_x_mm=1000,
        max_dims_y_mm=1000,
        max_dims_z_mm=1000,
        distance_from_exit_m=12.5
    )
    
    user = User(
        login="warehouseman1",
        email="user@primus.com",
        password_hash="hashed_secret",
        role=UserRole.WAREHOUSEMAN
    )
    
    db_session.add_all([product, rack, user])
    await db_session.commit()
    await db_session.refresh(product)
    await db_session.refresh(rack)
    await db_session.refresh(user)
    
    # 2. Create Stock Item
    stock_item = StockItem(
        product_id=product.id,
        rack_id=rack.id,
        position_row=1,
        position_col=1,
        expiry_date=date(2026, 12, 31),
        received_by_id=user.id
    )
    
    db_session.add(stock_item)
    await db_session.commit()
    await db_session.refresh(stock_item)
    
    # 3. Verify
    assert stock_item.id is not None
    # Check relationships
    query = select(StockItem).where(StockItem.id == stock_item.id)
    result = await db_session.execute(query)
    fetched_item = result.scalars().first()
    
    
    assert fetched_item.product_id == product.id
    assert fetched_item.rack_id == rack.id
    assert fetched_item.received_by_id == user.id

from app.models.alert import Alert, AlertType

@pytest.mark.asyncio
async def test_create_alert_with_weight(db_session: AsyncSession):
    alert = Alert(
        alert_type=AlertType.WEIGHT,
        message="Weight exceeded on Rack A-01",
        last_valid_weight=50.5,
        is_resolved=False
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    assert alert.id is not None
    assert alert.last_valid_weight == 50.5
    assert alert.alert_type == AlertType.WEIGHT
