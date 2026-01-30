import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.rack import Rack
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from app.database.models.user import User
from datetime import datetime
from sqlalchemy import select

@pytest.mark.asyncio
async def test_update_rack_constraints(
    authorized_admin_client: AsyncClient,
    db_session: AsyncSession
):
    """Test validation constraints when updating a rack with items."""
    
    # 1. Setup Data
    # Create a Rack
    rack = Rack(
        designation="R-CONSTRAINTS",
        max_weight_kg=1000.0,
        max_dims_x_mm=1000, max_dims_y_mm=1000, max_dims_z_mm=1000,
        temp_min=10.0, temp_max=20.0,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.flush()

    # Create Product
    product = ProductDefinition(
        name="Sensitive Item",
        barcode="SENSITIVE-001",
        weight_kg=100.0,
        dims_x_mm=500, dims_y_mm=500, dims_z_mm=500,
        req_temp_min=12.0, req_temp_max=18.0, # Requires [12, 18]
        expiry_days=30
    )
    db_session.add(product)
    await db_session.flush()

    # Get User for receiver
    user_result = await db_session.execute(select(User).limit(1))
    user = user_result.scalar_one()

    # Add Item to Rack
    item = StockItem(
        rack_id=rack.id,
        product_id=product.id,
        position_row=1, position_col=1,
        entry_date=datetime.now(),
        expiry_date=datetime.now(),
        received_by_id=user.id
    )
    db_session.add(item)
    await db_session.commit()

    # Helper to assert failure
    async def assert_update_fail(payload, expect_msg):
        response = await authorized_admin_client.put(f"/api/v1/racks/{rack.id}", json=payload)
        assert response.status_code == 400
        assert expect_msg in response.json()['detail']

    expected_error = "These update values are not valid for the stock items on this rack"

    # --- Test Cases ---

    # 1. Weight Constraint
    # Current load 100kg. Try to reduce capacity to 50kg.
    await assert_update_fail({"max_weight_kg": 50.0}, expected_error)

    # 2. Dimensions Constraint
    # Current item 500x500x500. Try to reduce max dims below that.
    await assert_update_fail({"max_dims_x_mm": 400}, expected_error)
    await assert_update_fail({"max_dims_y_mm": 400}, expected_error)
    await assert_update_fail({"max_dims_z_mm": 400}, expected_error)

    # 3. Temperature Constraint
    # Item needs [12, 18]. Rack is [10, 20].
    
    # Try to set Rack Min Temp to 11. Valid? Yes (11 < 12).
    # Wait, my logic: 
    # if new_temp_min < max_req_min: error
    # Item req min is 12. 
    # If I set Rack Min to 11. 11 < 12? Yes. Error? 
    # Wait, if Item requires AT LEAST 12 degrees. 
    # And Rack CAN go down to 11 degrees. 
    # Then the rack is UNSAFE because it might be 11 degrees, which is too cold for item requiring 12.
    # So Rack Min must be >= Item Min Req.
    # So new_temp_min (11) < max_req_min (12) -> ERROR. Correct.
    await assert_update_fail({"temp_min": 11.0}, expected_error)

    # Valid change: set Rack Min to 12.0. 12 < 12 is false. OK.
    # Actually wait. If Rack Min is 12. It means rack can be 12. Item needs >= 12. OK.
    
    # Try to set Rack Min to 13.0. 13 < 12 is false. OK.
    # If Rack Min is 13. Rack is always >= 13. Item needs >= 12. So Safe.

    # Try Max Temp. Item needs <= 18.
    # If I set Rack Max to 19. Rack might be 19. Item needs <= 18. Unsafe.
    # new_temp_max (19) > min_req_max (18) -> ERROR.
    await assert_update_fail({"temp_max": 21.0}, expected_error) # 21 > 18
    await assert_update_fail({"temp_max": 18.1}, expected_error)

    # 4. Success Case
    # Update to valid values
    payload_valid = {
        "max_weight_kg": 200.0, # > 100
        "max_dims_x_mm": 600,   # > 500
        "temp_min": 12.0,       # >= 12
        "temp_max": 18.0        # <= 18
    }
    response = await authorized_admin_client.put(f"/api/v1/racks/{rack.id}", json=payload_valid)
    assert response.status_code == 200
    data = response.json()
    assert data["max_weight_kg"] == 200.0
    assert data["temp_min"] == 12.0


