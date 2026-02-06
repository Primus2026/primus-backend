import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.rack import Rack
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import select
from datetime import datetime

@pytest.mark.asyncio
async def test_create_rack_success(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test successful creation of a rack by an admin."""
    payload = {
        "designation": "R-NEW",
        "max_weight_kg": 1000,
        "max_dims_x_mm": 2000,
        "max_dims_y_mm": 1000,
        "max_dims_z_mm": 800,
        "temp_min": 15,
        "temp_max": 25,
        "rows_m": 5,
        "cols_n": 5,
        "comment": "New Rack"
    }
    
    response = await authorized_admin_client.post("/api/v1/racks/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["designation"] == payload["designation"]
    assert "id" in data
    
    # Verify in DB
    result = await db_session.execute(select(Rack).where(Rack.designation == "R-NEW"))
    rack = result.scalar_one_or_none()
    assert rack is not None
    assert rack.comment == "New Rack"

@pytest.mark.asyncio
async def test_create_rack_duplicate(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test ensure unique designation constraint."""
    # Pre-create rack
    rack = Rack(
        designation="R-DUP",
        max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=15, temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.commit()
    
    payload = {
        "designation": "R-DUP",
        "max_weight_kg": 500,
        "max_dims_x_mm": 2000,
        "max_dims_y_mm": 1000,
        "max_dims_z_mm": 800,
        "temp_min": 15,
        "temp_max": 25,
        "rows_m": 5,
        "cols_n": 5
    }
    
    response = await authorized_admin_client.post("/api/v1/racks/", json=payload)
    assert response.status_code == 400
    assert "Półka o tym oznaczeniu już istnieje" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_rack_success(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test getting a rack by ID."""
    rack = Rack(
        designation="R-GET",
        max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=15, temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.commit()
    
    response = await authorized_admin_client.get(f"/api/v1/racks/{rack.id}")
    assert response.status_code == 200
    assert response.json()["designation"] == "R-GET"

@pytest.mark.asyncio
async def test_get_rack_not_found(
    authorized_admin_client: AsyncClient
):
    """Test getting a non-existent rack."""
    response = await authorized_admin_client.get("/api/v1/racks/999999")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_update_rack_success(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test updating a rack."""
    rack = Rack(
        designation="R-UPDATE",
        max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=15, temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.commit()
    
    payload = {
        "id": rack.id,
        "designation": "R-UPDATED",
        "comment": "Updated Comment"
    }
    
    response = await authorized_admin_client.put(f"/api/v1/racks/{rack.id}", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["designation"] == "R-UPDATED"
    assert data["comment"] == "Updated Comment"
    # Check that other fields remained
    assert data["max_weight_kg"] == 1000.0

@pytest.mark.asyncio
async def test_delete_rack_success(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test deleting an empty rack."""
    rack = Rack(
        designation="R-DELETE",
        max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=15, temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.commit()
    
    response = await authorized_admin_client.delete(f"/api/v1/racks/{rack.id}")
    assert response.status_code == 200
    
    # Verify it's gone
    result = await db_session.execute(select(Rack).where(Rack.id == rack.id))
    assert result.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_delete_rack_not_empty(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test that a rack with items cannot be deleted."""
    # Create rack
    rack = Rack(
        designation="R-FULL",
        max_weight_kg=1000, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        temp_min=15, temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.flush()
    
    # Create product and item
    product = ProductDefinition(
        name="Item",
        barcode="999",
        expiry_days=30,
        weight_kg=1,
        dims_x_mm=10, dims_y_mm=10, dims_z_mm=10,
        req_temp_min=0, req_temp_max=100
    )
    db_session.add(product)
    await db_session.flush()
    
    # We need a user for 'received_by'
    # In tests, usually need to query the existing admin or create a user.
    # The 'authorized_admin_client' fixture creates a user, we can fetch it.
    from app.database.models.user import User
    user = await db_session.execute(select(User).limit(1))
    user = user.scalar_one()

    item = StockItem(
        rack_id=rack.id,
        product_id=product.id,
        entry_date=datetime.now(),
        expiry_date=datetime.now(),
        position_row=1,
        position_col=1,
        received_by_id=user.id
    )
    db_session.add(item)
    await db_session.commit()
    
    response = await authorized_admin_client.delete(f"/api/v1/racks/{rack.id}")
    assert response.status_code == 400
    assert "Regał ma produkty, musi być pusty" in response.json().get("detail", "")

@pytest.mark.asyncio
async def test_create_rack_invalid_data(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test validation errors for RackCreate."""
    # 1. Invalid temperature range (min > max)
    payload_temp = {
        "designation": "R-TEMP-FAIL",
        "max_weight_kg": 1000, "max_dims_x_mm": 1000, "max_dims_y_mm": 1000, "max_dims_z_mm": 1000,
        "temp_min": 30, "temp_max": 20, # Invalid
        "rows_m": 5, "cols_n": 5
    }
    response = await authorized_admin_client.post("/api/v1/racks/", json=payload_temp)
    assert response.status_code == 422 # Pydantic Validation Error

    # 2. Negative values
    payload_neg = {
        "designation": "R-NEG-FAIL",
        "max_weight_kg": -100, # Invalid
        "max_dims_x_mm": 1000, "max_dims_y_mm": 1000, "max_dims_z_mm": 1000,
        "temp_min": 10, "temp_max": 20,
        "rows_m": 5, "cols_n": 5
    }
    response = await authorized_admin_client.post("/api/v1/racks/", json=payload_neg)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_update_rack_validation(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test validation errors for RackUpdate."""
    # Create valid rack first
    rack = Rack(
        designation="R-VAL-UPDATE",
        max_weight_kg=1000, max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=10, temp_max=20,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.commit()

    # 1. Partial update resulting in invalid temp range (Service Layer Check)
    # Existing: min=10, max=20. Update max=5 -> min=10 > max=5 (Invalid)
    payload_temp = {"temp_max": 5}
    response = await authorized_admin_client.put(f"/api/v1/racks/{rack.id}", json=payload_temp)
    assert response.status_code == 400
    assert "Minimalna temperatura nie może być wyższa niż maksymalna temperatura" in response.json()["detail"]

    # 2. Negative value update (Pydantic Check)
    payload_neg = {"distance_from_exit_m": -10}
    response = await authorized_admin_client.put(f"/api/v1/racks/{rack.id}", json=payload_neg)
    assert response.status_code == 422
