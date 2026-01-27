

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.tasks.ai_tasks import retrain_model_task, predict_task

@pytest.fixture(autouse=True)
def mock_logger():
    with patch("app.tasks.ai_tasks.logger"):
        yield

def test_retrain_model_task():
    """Verify task calls service method"""
    with patch("app.services.ai_service.AIService.retrain_model") as mock_retrain:
        result = retrain_model_task()
        
        mock_retrain.assert_called_once()
        assert result["status"] == "success"

def test_predict_task():
    """Verify predict task flow"""
    s3_key = "temp/image.jpg"
    
    with patch("app.core.storage.storage.get", new_callable=AsyncMock) as mock_get, \
        patch("app.core.storage.storage.delete", new_callable=AsyncMock) as mock_delete, \
        patch("app.services.ai_service.AIService.predict") as mock_predict, \
        patch("builtins.open", new_callable=MagicMock), \
        patch("os.path.exists") as mock_exists, \
        patch("os.remove") as mock_remove, \
        patch("app.tasks.ai_tasks.fetch_product_details") as mock_fetch_details:
         
        # Setup Mocks
        mock_get.return_value = b"fake_image_bytes"
         
        with patch("aiofiles.open", new_callable=MagicMock) as mock_aio_open:
             mock_f = AsyncMock()
             mock_aio_open.return_value.__aenter__.return_value = mock_f
             
             mock_exists.return_value = True
             mock_predict.return_value = (101, 0.95)
             mock_fetch_details.return_value = ("Test Product", "123456")
             
             # EXECUTE
             result = predict_task(s3_key)
             
             # VERIFY
             mock_get.assert_called_with(s3_key)
             mock_f.write.assert_awaited_with(b"fake_image_bytes")
             
             assert mock_predict.called
             args = mock_predict.call_args[0]
             assert str(args[0]).endswith(".jpg")
             
             assert mock_remove.called
             mock_delete.assert_called_with(s3_key)
             
             assert result["product_id"] == 101
             assert result["name"] == "Test Product"
             assert result["barcode"] == "123456"

