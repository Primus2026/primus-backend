import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_trigger_import_task(
    async_client: AsyncClient,
    admin_token: str
):
    """Test POST /import triggers celery task and returns task_id"""
    
    # Mock the Celery task 'delay' method
    with patch("app.tasks.csv_import.import_racks.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "test-task-id-123"
        mock_delay.return_value = mock_task

        csv_content = "Oznaczenie;MaxWagaKg;...\nR-1;100;..."
        files = {"file": ("racks.csv", csv_content, "text/csv")}

        response = await async_client.post(
            "/api/v1/racks/import",
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-id-123"
        assert data["status"] == "processing"
        
        # Verify delay was called
        mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_get_import_status_pending(
    async_client: AsyncClient,
    admin_token: str
):
    """Test GET /import/{id} for PENDING state"""
    
    with patch("app.core.celery_worker.celery_app.AsyncResult") as mock_async_result:
        mock_result = MagicMock()
        mock_result.state = "PENDING"
        mock_async_result.return_value = mock_result
        
        response = await async_client.get(
            "/api/v1/racks/import/pending-task-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_get_import_status_failure(
    async_client: AsyncClient,
    admin_token: str
):
    """Test GET /import/{id} for FAILURE state"""
    
    with patch("app.core.celery_worker.celery_app.AsyncResult") as mock_async_result:
        mock_result = MagicMock()
        mock_result.state = "FAILURE"
        mock_result.result = ValueError("Something went wrong")
        mock_async_result.return_value = mock_result
        
        response = await async_client.get(
            "/api/v1/racks/import/failed-task-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "Something went wrong" in data["error"]


@pytest.mark.asyncio
async def test_get_import_status_success(
    async_client: AsyncClient,
    admin_token: str
):
    """Test GET /import/{id} for SUCCESS state"""
    
    # Result matches ImportResult model structure (as a dict)
    success_result = {
        "message": "Done",
        "summary": {
            "created_count": 5,
            "updated_count": 0,
            "skipped_count": 0,
            "skipped_details": []
        }
    }
    
    with patch("app.core.celery_worker.celery_app.AsyncResult") as mock_async_result:
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.result = success_result
        mock_async_result.return_value = mock_result
        
        response = await async_client.get(
            "/api/v1/racks/import/success-task-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["summary"]["created_count"] == 5



@pytest.mark.asyncio
async def test_import_permissions(
    async_client: AsyncClient,
    admin_token: str,
    warehouseman_token: str
):
    """Test import permissions"""
    
    # Mock the Celery task 'delay' method to prevent hanging
    with patch("app.tasks.csv_import.import_racks.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "test-task-id-123"
        mock_delay.return_value = mock_task

        # Admin should have permission
        response = await async_client.post(
            "/api/v1/racks/import",
            files={"file": ("racks.csv", "Oznaczenie;MaxWagaKg;...\nR-1;100;...", "text/csv")},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        # User should not have permission
        response = await async_client.post(
            "/api/v1/racks/import",
            files={"file": ("racks.csv", "Oznaczenie;MaxWagaKg;...\nR-1;100;...", "text/csv")},
            headers={"Authorization": f"Bearer {warehouseman_token}"}
        )
        assert response.status_code == 403
