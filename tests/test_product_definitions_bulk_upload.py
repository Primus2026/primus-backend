import pytest
import asyncio
from unittest.mock import MagicMock, patch
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_bulk_upload_images_endpoint(
    async_client: AsyncClient,
    admin_token: str
):
    """Test POST /product_definitions/bulk-images triggers celery task"""
    
    # Mock the Celery task 'delay'
    # IMPORTANT: Adjust the patch path to match where it is imported in the router
    # In `product_definition_CRUD.py`, we import `bulk_upload_task` which is an alias.
    # We should patch the task object itself where it is defined or where it is used.
    # The safest is patching the prompt where it is used in the router.
    # Router: `app.api.v1.endpoints.product_definition_CRUD.bulk_upload_task`
    
    # Patch the task in the location where it's DEFINED (or imported from)
    # Since product_definition_CRUD imports it from tasks, patching it in tasks module is safer/easier
    # provided the import happens at runtime or we patch where it is pointed to.
    # However, patching at source `app.tasks.product_definition_tasks.bulk_upload_images` works if
    # the code uses that object.
    
    with patch("app.api.v1.endpoints.product_definition_CRUD.bulk_upload_task") as mock_task_obj:
        # Configure the delay method on the task object
        mock_task_instance = MagicMock()
        mock_task_instance.id = "bulk-upload-task-id-123"
        
        mock_task_obj.delay.return_value = mock_task_instance

        files = [
            ("files", ("image1.jpg", b"fake_content_1", "image/jpeg")),
            ("files", ("image2.jpg", b"fake_content_2", "image/jpeg"))
        ]

        response = await async_client.post(
            "/api/v1/product_definitions/bulk-images",
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "bulk-upload-task-id-123"
        assert data["status"] == "processing"
        
        # Verify delay was called
        mock_task_obj.delay.assert_called_once()
        # Verify call args
        args, _ = mock_task_obj.delay.call_args
        temp_dir = args[0]
        # Should be inside temp_uploads
        assert "temp_uploads" in temp_dir


@pytest.mark.asyncio
async def test_get_bulk_upload_status(
    async_client: AsyncClient,
    admin_token: str
):
    """Test GET /product_definitions/bulk-images/{task_id}"""
    
    # Mock result matching ImportSummary
    success_result = {
        "total_processed": 10,
        "success_count": 8,
        "error_count": 2,
        "errors": ["Err1", "Err2"]
    }
    
    with patch("app.core.celery_worker.celery_app.AsyncResult") as mock_async_result:
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.result = success_result
        mock_async_result.return_value = mock_result
        
        response = await async_client.get(
            "/api/v1/product_definitions/bulk-images/test-task-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["summary"]["success_count"] == 8
        assert data["summary"]["error_count"] == 2
