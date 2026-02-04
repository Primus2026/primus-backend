import pytest
from httpx import AsyncClient
from app.database.models import ProductDefinition, StockItem, ProductStats
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

@pytest.fixture
async def sample_product_definition(db_session: AsyncSession):
    product = ProductDefinition(
        name="Test Product",
        barcode="123456789",
        req_temp_min=2.0,
        req_temp_max=8.0,
        weight_kg=1.5,
        dims_x_mm=100,
        dims_y_mm=200,
        dims_z_mm=50,
        is_dangerous=False,
        comment="Test Comment",
        expiry_days=30
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product

@pytest.mark.asyncio
async def test_delete_product_definition_with_stock_items(async_client: AsyncClient, admin_token: str, sample_product_definition, db_session: AsyncSession):
    # Create a stock item
    from datetime import datetime, date, timedelta
    
    # We need a rack first (mock or create)
    from app.database.models.rack import Rack
    rack = Rack(
        designation="A-01-01-TEST",
        rows_m=5,
        cols_n=5,
        temp_min=0,
        temp_max=10,
        max_weight_kg=1000,
        max_dims_x_mm=1000,
        max_dims_y_mm=1000,
        max_dims_z_mm=1000
    )
    db_session.add(rack)
    await db_session.commit()
    await db_session.refresh(rack)

    # We need a user (receiver)
    # Assuming test env sets up users or we can pick one.
    # Usually admin_token implies a user exists, but we need ID for FK.
    from app.database.models.user import User
    user = (await db_session.execute(select(User))).scalars().first()
    
    stock_item = StockItem(
        product_id=sample_product_definition.id,
        rack_id=rack.id,
        position_row=1,
        position_col=1,
        expiry_date=date.today() + timedelta(days=30),
        received_by_id=user.id
    )
    db_session.add(stock_item)
    await db_session.commit()

    # Try to delete
    response = await async_client.delete(
        f"/api/v1/product_definitions/{sample_product_definition.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 409
    assert "Cannot delete product definition" in response.json()["detail"]

@pytest.mark.asyncio
async def test_delete_product_definition_with_stats_success(async_client: AsyncClient, admin_token: str, sample_product_definition, db_session: AsyncSession):
    # Create stats
    stats = ProductStats(
        product_id=sample_product_definition.id,
        pick_count=5
    )
    db_session.add(stats)
    await db_session.commit()
    
    # Try to delete
    response = await async_client.delete(
        f"/api/v1/product_definitions/{sample_product_definition.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    
    # Refresh session to see DB changes made by app
    db_session.expire_all()
    
    # Verify deletion of stats
    result = await db_session.execute(select(ProductStats).where(ProductStats.product_id == sample_product_definition.id))
    assert result.scalar_one_or_none() is None
    
    # Verify deletion of product
    result = await db_session.get(ProductDefinition, sample_product_definition.id)
    assert result is None
