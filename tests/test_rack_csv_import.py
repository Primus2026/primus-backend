import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.rack import Rack
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from app.database.models.user import User
from sqlalchemy import select
from datetime import datetime

@pytest.mark.asyncio
async def test_import_racks_success(
    async_client: AsyncClient, 
    admin_token: str, 
    db_session: AsyncSession
):
    """Test successful import of racks from CSV."""
    csv_content = """Oznaczenie;MaxWagaKg;MaxSzerokoscMm;MaxWysokoscMm;MaxGlebokoscMm;TempMin;TempMax;M;N;Komentarz
R-100;1000;2000;1000;800;15;25;5;5;Test
R-101;500;1500;800;600;10;20;5;5;Test2
"""
    files = {"file": ("racks.csv", csv_content, "text/csv")}
    
    response = await async_client.post(
        "/api/v1/racks/import",
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()
    assert data["summary"]["created_count"] == 2
    assert data["summary"]["updated_count"] == 0
    assert data["summary"]["skipped_count"] == 0
    
    # Verify DB
    result = await db_session.execute(select(Rack).where(Rack.designation == "R-100"))
    rack = result.scalars().first()
    assert rack is not None
    assert rack.max_weight_kg == 1000
    
@pytest.mark.asyncio
async def test_import_racks_conflict_weight(
    async_client: AsyncClient, 
    admin_token: str, 
    db_session: AsyncSession
):
    """Test import fails validation if new weight is less than existing items total weight."""
    user = await db_session.scalar(select(User))
    
    # 1. Setup existing rack and item
    rack = Rack(
        designation="R-CONFLICT",
        max_weight_kg=1000,
        max_dims_x_mm=2000,
        max_dims_y_mm=1000,
        max_dims_z_mm=800,
        temp_min=15,
        temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.flush()
    
    product = ProductDefinition(
        name="Heavy Item",
        barcode="1001",
        expiry_days=365,
        weight_kg=800, # Current usage
        dims_x_mm=100, dims_y_mm=100, dims_z_mm=100,
        req_temp_min=15, req_temp_max=25
    )
    db_session.add(product)
    await db_session.flush()
    
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
    
    # 2. Try to update max_weight to 500 (Less than 800)
    # We add 3 valid rows to ensure conflict rate < 30% (1/4 = 25%)
    csv_content = """Oznaczenie;MaxWagaKg;MaxSzerokoscMm;MaxWysokoscMm;MaxGlebokoscMm;TempMin;TempMax;M;N;Komentarz
R-CONFLICT;500;2000;1000;800;15;25;5;5;Conflict
R-VALID1;1000;2000;1000;800;15;25;5;5;Valid
R-VALID2;1000;2000;1000;800;15;25;5;5;Valid
R-VALID3;1000;2000;1000;800;15;25;5;5;Valid
"""
    files = {"file": ("racks.csv", csv_content, "text/csv")}
    
    response = await async_client.post(
        "/api/v1/racks/import",
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()
    assert data["summary"]["skipped_count"] == 1
    assert "New max weight 500.0kg < current load 800.0kg" in data["summary"]["skipped_details"][0]

@pytest.mark.asyncio
async def test_import_racks_conflict_dimensions(
    async_client: AsyncClient, 
    admin_token: str, 
    db_session: AsyncSession
):
    """Test conflict when new rack dims are smaller than an existing item."""
    user = await db_session.scalar(select(User))

    # 1. Setup
    rack = Rack(
        designation="R-DIM-CONFLICT",
        max_weight_kg=1000, max_dims_x_mm=2000, max_dims_y_mm=1000, max_dims_z_mm=800,
        temp_min=15, temp_max=25,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.flush()
    
    product = ProductDefinition(
        name="Wide Item",
        barcode="1002",
        expiry_days=365,
        weight_kg=100,
        dims_x_mm=1800, # Large Width
        dims_y_mm=100, dims_z_mm=100,
        req_temp_min=15, req_temp_max=25
    )
    db_session.add(product)
    await db_session.flush()
    
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
    
    # 2. Update rack to width 1000 (Smaller than item width 1800)
    # Add valid rows to avoid abort threshold
    csv_content = """Oznaczenie;MaxWagaKg;MaxSzerokoscMm;MaxWysokoscMm;MaxGlebokoscMm;TempMin;TempMax;M;N
R-DIM-CONFLICT;1000;1000;1000;800;15;25;5;5
R-VALID1;1000;2000;1000;800;15;25;5;5
R-VALID2;1000;2000;1000;800;15;25;5;5
R-VALID3;1000;2000;1000;800;15;25;5;5
"""
    files = {"file": ("racks.csv", csv_content, "text/csv")}
    
    response = await async_client.post(
        "/api/v1/racks/import",
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()
    assert data["summary"]["skipped_count"] == 1
    assert "New width 1000mm < item width 1800mm" in data["summary"]["skipped_details"][0]

@pytest.mark.asyncio
async def test_import_racks_conflict_temp(
    async_client: AsyncClient, 
    admin_token: str, 
    db_session: AsyncSession
):
    """Test conflict when new temp range excludes existing item requirements."""
    user = await db_session.scalar(select(User))

    # 1. Setup
    rack = Rack(
        designation="R-TEMP-CONFLICT",
        max_weight_kg=1000, max_dims_x_mm=2000, max_dims_y_mm=1000, max_dims_z_mm=800,
        temp_min=10, temp_max=30,
        rows_m=5, cols_n=5
    )
    db_session.add(rack)
    await db_session.flush()
    
    product = ProductDefinition(
        name="Sensitive Item",
        barcode="1003",
        expiry_days=30,
        weight_kg=10,
        dims_x_mm=100, dims_y_mm=100, dims_z_mm=100,
        req_temp_min=15, req_temp_max=20 # Needs strict 15-20C
    )
    db_session.add(product)
    await db_session.flush()
    
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
    
    # 2. Update rack to 0-10C (Too cold for item requesting min 15)
    # Add valid rows to avoid abort threshold
    csv_content = """Oznaczenie;MaxWagaKg;MaxSzerokoscMm;MaxWysokoscMm;MaxGlebokoscMm;TempMin;TempMax;M;N
R-TEMP-CONFLICT;1000;2000;1000;800;0;10;5;5
R-VALID1;1000;2000;1000;800;15;25;5;5
R-VALID2;1000;2000;1000;800;15;25;5;5
R-VALID3;1000;2000;1000;800;15;25;5;5
"""
    files = {"file": ("racks.csv", csv_content, "text/csv")}
    
    response = await async_client.post(
        "/api/v1/racks/import",
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()
    assert data["summary"]["skipped_count"] == 1
    # Check for specific error message about min temp
    assert "New temp max 10.0 > item max req 20.0" in data["summary"]["skipped_details"][0] or \
           "New temp min 0.0 < item min req 15.0" in data["summary"]["skipped_details"][0]

@pytest.mark.asyncio
async def test_import_racks_abort_threshold(
    async_client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession
):
    """Test that import raises 400 if conflict rate > 30%."""
    user = await db_session.scalar(select(User))

    # Setup: 2 racks with items that will conflict
    # Rack A
    rackA = Rack(designation="R-A", max_weight_kg=100, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100, temp_min=15, temp_max=25, rows_m=5, cols_n=5)
    db_session.add(rackA)
    # Rack B
    rackB = Rack(designation="R-B", max_weight_kg=100, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100, temp_min=15, temp_max=25, rows_m=5, cols_n=5)
    db_session.add(rackB)
    await db_session.flush()
    
    # Add heavy items to both
    prod = ProductDefinition(
        name="Heavy",
        barcode="12345", # Added required
        expiry_days=30, # Added required
        weight_kg=90,
        dims_x_mm=10, dims_y_mm=10, dims_z_mm=10,
        req_temp_min=0, req_temp_max=100
    )
    db_session.add(prod)
    await db_session.flush()
    
    db_session.add(StockItem(
        rack_id=rackA.id, 
        product_id=prod.id, 
        entry_date=datetime.now(),
        expiry_date=datetime.now(),
        position_row=1,
        position_col=1,
        received_by_id=user.id
    ))
    db_session.add(StockItem(
        rack_id=rackB.id, 
        product_id=prod.id, 
        entry_date=datetime.now(),
        expiry_date=datetime.now(),
        position_row=1,
        position_col=1,
        received_by_id=user.id
    ))
    await db_session.commit()
    
    # CSV tries to update both to max_weight=50 (Conflict for both) + 1 new valid rack
    # Total 3 rows. 2 conflicts. 66% conflict rate. Should abort.
    csv_content = """Oznaczenie;MaxWagaKg;MaxSzerokoscMm;MaxWysokoscMm;MaxGlebokoscMm;TempMin;TempMax;M;N
R-A;50;100;100;100;15;25;5;5
R-B;50;100;100;100;15;25;5;5
R-NEW;100;100;100;100;15;25;5;5
"""
    files = {"file": ("racks.csv", csv_content, "text/csv")}
    
    response = await async_client.post(
        "/api/v1/racks/import",
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 400
    assert "Too many conflicts" in response.json()["detail"]

@pytest.mark.asyncio
async def test_import_permissions(
    async_client: AsyncClient,
    warehouseman_token: str
):
    """Test that non-admins cannot import."""
    csv_content = "designation;..."
    files = {"file": ("racks.csv", csv_content, "text/csv")}
    
    response = await async_client.post(
        "/api/v1/racks/import",
        files=files,
        headers={"Authorization": f"Bearer {warehouseman_token}"}
    )
    
    # Depending on implementation, might be 403 or 401 if role check fails
    assert response.status_code in [403]
