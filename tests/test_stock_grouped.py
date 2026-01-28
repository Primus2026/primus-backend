import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, date
from sqlalchemy import select

from app.database.models.product_definition import ProductDefinition
from app.database.models.stock_item import StockItem
from app.database.models.rack import Rack
from app.database.models.user import User

async def create_rack(db: AsyncSession, designation="A-01"):
    rack = Rack(
        designation=designation, 
        rows_m=5, 
        cols_n=10,
        temp_min=0,
        temp_max=25,
        max_weight_kg=1000,
        max_dims_x_mm=1000,
        max_dims_y_mm=1000,
        max_dims_z_mm=1000
    )
    db.add(rack)
    await db.commit()
    await db.refresh(rack)
    return rack

async def create_product(db: AsyncSession, name="Test Product", barcode="12345"):
    product = ProductDefinition(
        name=name,
        barcode=barcode,
        req_temp_min=0,
        req_temp_max=10,
        weight_kg=1.0,
        dims_x_mm=100,
        dims_y_mm=100,
        dims_z_mm=100,
        is_dangerous=False,
        comment="Test",
        expiry_days=365
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

async def create_stock_item(db: AsyncSession, product_id, rack_id, row, col, receiver_id, expiry_date):
    item = StockItem(
        product_id=product_id,
        rack_id=rack_id,
        position_row=row,
        position_col=col,
        received_by_id=receiver_id,
        expiry_date=expiry_date
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

@pytest.fixture
async def setup_stock_data(db_session: AsyncSession):
    # Setup data
    rack = await create_rack(db_session)
    product1 = await create_product(db_session, name="Apple", barcode="111")
    product2 = await create_product(db_session, name="Banana", barcode="222")
    product3 = await create_product(db_session, name="Carrot", barcode="333")
    
    # Get admin user (assumed to be created by fixtures used in test)
    # We need to find *some* user for the receiver_id
    result = await db_session.execute(select(User).limit(1))
    user = result.scalars().first()
    
    now = datetime.now()
    exp1 = now.date() + timedelta(days=10)
    exp2 = now.date() + timedelta(days=5) # Earlier
    exp3 = now.date() + timedelta(days=20)

    # Apple: 2 items, exp2 < exp1
    await create_stock_item(db_session, product1.id, rack.id, 1, 1, user.id, exp1)
    await create_stock_item(db_session, product1.id, rack.id, 1, 2, user.id, exp2)
    
    # Banana: 1 item
    await create_stock_item(db_session, product2.id, rack.id, 2, 1, user.id, exp3)
    
    # Carrot: 0 items (is product, but no items) => Should not appear if we group ONLY available stock? 
    # Current implementation: "Get products... then items". 
    # Logic was: fetch products, then fetch items. If product has no items, it results in empty list of items.
    
    return {"products": [product1, product2, product3], "rack": rack, "user": user}

@pytest.mark.asyncio
async def test_get_grouped_stocks_auth_required(async_client: AsyncClient):
    """Test that authentication is required"""
    response = await async_client.get("/api/v1/stock/")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_grouped_stocks_basic_structure(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_stock_data
):
    """Test standard response structure and logic"""
    response = await authorized_admin_client.get("/api/v1/stock/?limit=10")
    assert response.status_code == 200
    data = response.json()
    
    # Expecting 3 groups because we fetch products first, and 3 products exist
    assert len(data) == 3 
    
    # Verify product names
    names = [g["product"]["name"] for g in data]
    assert "Apple" in names
    assert "Banana" in names
    assert "Carrot" in names

@pytest.mark.asyncio
async def test_get_grouped_stocks_sorting(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_stock_data
):
    """Test that items within a group are sorted by expiry date"""
    response = await authorized_admin_client.get("/api/v1/stock/?name=Apple")
    assert response.status_code == 200
    data = response.json()
    
    apple_group = data[0]
    items = apple_group["stock_items"]
    assert len(items) == 2
    # Verify strict sorting: earlier date first
    assert items[0]["expiry_date"] < items[1]["expiry_date"]

@pytest.mark.asyncio
async def test_get_grouped_stocks_pagination(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_stock_data
):
    """Test pagination works for products"""
    # Page 1, Limit 2 => Should get first 2 products (alphabetical by default DB order, likely ID)
    response = await authorized_admin_client.get("/api/v1/stock/?page=1&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    # Page 2, Limit 2 => Should get remainder (1 product)
    response = await authorized_admin_client.get("/api/v1/stock/?page=2&limit=2")
    assert response.status_code == 200
    data_p2 = response.json()
    assert len(data_p2) == 1
    
    # Verify disjoint sets
    ids_p1 = {g["product"]["id"] for g in data}
    ids_p2 = {g["product"]["id"] for g in data_p2}
    assert ids_p1.isdisjoint(ids_p2)

@pytest.mark.asyncio
async def test_get_grouped_stocks_filtering(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_stock_data
):
    """Test filtering by product name"""
    # Case insensitive partial match
    response = await authorized_admin_client.get("/api/v1/stock/?name=app")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    assert data[0]["product"]["name"] == "Apple"

@pytest.mark.asyncio
async def test_get_grouped_stocks_validation_limits(authorized_admin_client: AsyncClient):
    """Test that invalid parameters are rejected"""
    # Page < 1
    response = await authorized_admin_client.get("/api/v1/stock/?page=0")
    assert response.status_code == 422
    
    response = await authorized_admin_client.get("/api/v1/stock/?limit=101")
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_get_grouped_stocks_empty(authorized_admin_client: AsyncClient, db_session: AsyncSession):
    """Test response when no products exist"""
    # Ensure DB is empty of products (might be tricky if other tests run in parallel or share DB, 
    # but db_session fixture usually provides isolation or we assume empty start if not setup)
    # Since we don't call setup_stock_data here, it should be empty relative to this test's context
    response = await authorized_admin_client.get("/api/v1/stock/")
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_get_grouped_stocks_no_items(
    authorized_admin_client: AsyncClient, 
    db_session: AsyncSession
):
    """Test product exists but has no stock items"""
    product = ProductDefinition(
        name="Ghost Product", barcode="GHOST", expiry_days=30, weight_kg=1,
        req_temp_min=0, req_temp_max=10, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10
    )
    db_session.add(product)
    await db_session.commit()
    
    response = await authorized_admin_client.get("/api/v1/stock/")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    assert data[0]["product"]["name"] == "Ghost Product"
    assert data[0]["stock_items"] == []
