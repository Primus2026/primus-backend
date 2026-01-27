import pytest
from httpx import AsyncClient
from app.database.models import ProductDefinition, UserRole
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock, patch, AsyncMock

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
async def test_create_product_definition(async_client: AsyncClient, admin_token: str):
    payload = {
        "name": "New Product",
        "barcode": "987654321",
        "req_temp_min": -5.0,
        "req_temp_max": 5.0,
        "weight_kg": 0.5,
        "dims_x_mm": 50,
        "dims_y_mm": 50,
        "dims_z_mm": 50,
        "is_dangerous": True,
        "comment": "New Comment",
        "expiry_days": 180
    }
    
    response = await async_client.post(
        "/api/v1/product_definitions/",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["barcode"] == payload["barcode"]
    assert "id" in data

@pytest.mark.asyncio
async def test_create_product_definition_duplicate(async_client: AsyncClient, admin_token: str, sample_product_definition):
    # Try to create product with same barcode
    payload = {
        "name": "Duplicate Product",
        "barcode": sample_product_definition.barcode,
        "req_temp_min": 0,
        "req_temp_max": 10,
        "weight_kg": 1,
        "dims_x_mm": 10,
        "dims_y_mm": 10,
        "dims_z_mm": 10,
        "is_dangerous": False,
        "comment": "",
        "expiry_days": 10
    }
    
    response = await async_client.post(
        "/api/v1/product_definitions/",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_get_product_definition(async_client: AsyncClient, admin_token: str, sample_product_definition):
    response = await async_client.get(
        f"/api/v1/product_definitions/{sample_product_definition.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_product_definition.id
    assert data["barcode"] == sample_product_definition.barcode

@pytest.mark.asyncio
async def test_get_product_definitions_list(async_client: AsyncClient, admin_token: str, sample_product_definition):
    response = await async_client.get(
        "/api/v1/product_definitions/",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [item["id"] for item in data]
    assert sample_product_definition.id in ids

@pytest.mark.asyncio
async def test_delete_product_definition(async_client: AsyncClient, admin_token: str, sample_product_definition):
    response = await async_client.delete(
        f"/api/v1/product_definitions/{sample_product_definition.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    
    # Verify deletion
    response = await async_client.get(
        f"/api/v1/product_definitions/{sample_product_definition.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_upload_image_single(async_client: AsyncClient, admin_token: str, sample_product_definition):
    # Mock file upload
    # We use a real file I/O since we can control MEDIA_ROOT in tests
    files = {"file": ("test.jpg", b"fake_image_content", "image/jpeg")}
    
    # Mock the storage.save method
    with patch("app.services.product_definition_service.storage.save", new_callable=AsyncMock) as mock_save:
        mock_save.return_value = "product_images/test.jpg"
        
        response = await async_client.post(
            f"/api/v1/product_definitions/{sample_product_definition.id}/upload_image",
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["photo_path"] is not None
        assert "product_images/" in data["photo_path"]
        
        # Verify storage.save was called
        mock_save.assert_called_once()

@pytest.mark.asyncio
async def test_get_product_definition_not_found(async_client: AsyncClient, admin_token: str):
    response = await async_client.get(
        "/api/v1/product_definitions/999999",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_product_definition_not_found(async_client: AsyncClient, admin_token: str):
    response = await async_client.delete(
        "/api/v1/product_definitions/999999",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_create_product_definition_unauthorized(async_client: AsyncClient):
    payload = {
        "name": "Unauthorized Product",
        "barcode": "000000000",
        "req_temp_min": 0,
        "req_temp_max": 10,
        "weight_kg": 1,
        "dims_x_mm": 10,
        "dims_y_mm": 10,
        "dims_z_mm": 10,
        "is_dangerous": False,
        "comment": "",
        "expiry_days": 10
    }
    response = await async_client.post(
        "/api/v1/product_definitions/",
        json=payload,
    )
    # 401 Unauthorized
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_product_definition_unauthorized(async_client: AsyncClient, sample_product_definition):
    response = await async_client.get(
        f"/api/v1/product_definitions/{sample_product_definition.id}",
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_upload_image_product_not_found(async_client: AsyncClient, admin_token: str):
    files = {"file": ("test.jpg", b"fake_image", "image/jpeg")}
    response = await async_client.post(
        "/api/v1/product_definitions/99999/upload_image",
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 404
