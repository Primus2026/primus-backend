import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, patch

@pytest.mark.asyncio
async def test_import_product_definitions_csv(async_client: AsyncClient, admin_token: str):
    """Test POST /product_definitions/import_csv triggers celery task"""
    
    with patch("app.api.v1.endpoints.product_definition_CRUD.import_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "csv-import-task-id-123"
        mock_delay.return_value = mock_task

        csv_content = """#Nazwa;Id;Zdjecie;TempMin;TempMax;Waga;SzerokoscMm;WysokoscMm;GlebokoscMm;Komentarz;TerminWaznosciDni;CzyNiebezpieczny
TestProd;12345;img.jpg;2;8;1.5;100;200;50;Comment;30;FALSE"""
        
        files = {"file": ("products.csv", csv_content, "text/csv")}

        response = await async_client.post(
            "/api/v1/product_definitions/import_csv",
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "csv-import-task-id-123"
        assert data["status"] == "processing"
        
        mock_delay.assert_called_once()

@pytest.mark.asyncio
async def test_get_import_csv_status(async_client: AsyncClient, admin_token: str):
    """Test GET /product_definitions/import_csv/{task_id}"""
    
    with patch("app.core.celery_worker.celery_app.AsyncResult") as mock_async_result:
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.result = {"status": "completed", "message": "Imported 1 products"}
        mock_async_result.return_value = mock_result
        
        response = await async_client.get(
            "/api/v1/product_definitions/import_csv/test-task-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        # The ImportResult model might behave slightly differently depending on how task.result is structured
        # The API code handles checks for "status" key.
