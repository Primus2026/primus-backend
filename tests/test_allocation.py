import pytest
import logging
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.product_definition import ProductDefinition, FrequencyClass
from app.database.models.rack import Rack
from app.database.models.user import User

# Configure logging to see our service logs
logging.basicConfig(level=logging.INFO)

async def create_user(db: AsyncSession):
    # Check if user exists first to avoid unique constraint error if multiple tests run
    result = await db.execute(select(User).limit(1))
    user = result.scalars().first()
    if user: return user
    
    # Or rely on fixture admin_token which creates user
    # But for specialized tests we might need ID
    pass 

async def create_rack(db: AsyncSession, designation, distance, max_weight=1000, temp_min=0, temp_max=30):
    rack = Rack(
        designation=designation, 
        rows_m=5, 
        cols_n=10,
        temp_min=temp_min,
        temp_max=temp_max,
        max_weight_kg=max_weight,
        max_dims_x_mm=1000,
        max_dims_y_mm=1000,
        max_dims_z_mm=1000,
        distance_from_exit_m=distance
    )
    db.add(rack)
    await db.commit()
    await db.refresh(rack)
    return rack

async def create_product(db, name, barcode, freq_class: FrequencyClass, weight=1.0, temp_min=5, temp_max=25):
    product = ProductDefinition(
        name=name,
        barcode=barcode,
        req_temp_min=temp_min,
        req_temp_max=temp_max,
        weight_kg=weight,
        dims_x_mm=100,
        dims_y_mm=100,
        dims_z_mm=100,
        is_dangerous=False,
        comment="Test",
        expiry_days=365,
        frequency_class=freq_class
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@pytest.fixture
async def setup_warehouse(db_session: AsyncSession):
    # Create Racks with different distances
    # A: Closest
    # C: Farthest
    # B: Median
    
    # Distances: 5, 10, 25, 50, 100
    # Median is 25. Range [15, 35].
    
    r1 = await create_rack(db_session, "R-05", 5.0)
    r2 = await create_rack(db_session, "R-10", 10.0)
    r3 = await create_rack(db_session, "R-25", 25.0) # Median
    r4 = await create_rack(db_session, "R-50", 50.0)
    r5 = await create_rack(db_session, "R-100", 100.0)
    
    return [r1, r2, r3, r4, r5]

@pytest.mark.asyncio
async def test_allocation_class_a(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_warehouse
):
    """Class A should go to closest rack (R-05)"""
    prod = await create_product(db_session, "Prod A", "A111", FrequencyClass.A)
    
    response = await authorized_admin_client.post("/api/v1/stock/inbound/", json={"barcode": "A111"})
    assert response.status_code == 201, response.text
    data = response.json()
    
    assert data["rack_designation"] == "R-05"

@pytest.mark.asyncio
async def test_allocation_class_c(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_warehouse
):
    """Class C should go to farthest rack (R-100)"""
    prod = await create_product(db_session, "Prod C", "C111", FrequencyClass.C)
    
    response = await authorized_admin_client.post("/api/v1/stock/inbound/", json={"barcode": "C111"})
    assert response.status_code == 201, response.text
    data = response.json()
    
    assert data["rack_designation"] == "R-100"

@pytest.mark.asyncio
async def test_allocation_class_b(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession,
    setup_warehouse
):
    """Class B should go to or near median rack (R-25)"""
    prod = await create_product(db_session, "Prod B", "B111", FrequencyClass.B)
    
    # Median is 25. Range [15, 35]. Only R-25 fits perfectly.
    # R-10 is 10 (abs diff 15). R-50 is 50 (abs diff 25).
    
    response = await authorized_admin_client.post("/api/v1/stock/inbound/", json={"barcode": "B111"})
    assert response.status_code == 201, response.text
    data = response.json()
    
    assert data["rack_designation"] == "R-25"

@pytest.mark.asyncio
async def test_allocation_constraints(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test physical constraints"""
    # Rack with low weight limit
    await create_rack(db_session, "R-Weak", 10.0, max_weight=5.0) # Max 5kg
    
    # Product heavy
    prod = await create_product(db_session, "Heavy", "H111", FrequencyClass.A, weight=10.0)
    
    response = await authorized_admin_client.post("/api/v1/stock/inbound/", json={"barcode": "H111"})
    assert response.status_code == 400
    assert "requirements" in response.text
