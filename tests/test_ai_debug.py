import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
from app.tasks.ai_tasks import predict_task
from app.services.ai_service import AIService
# We need to ensure ultralytics is patchable
import sys
mock_ultralytics = MagicMock()
sys.modules["ultralytics"] = mock_ultralytics

# Mock setup
@pytest.fixture
def mock_settings():
    with patch("app.services.ai_service.settings") as mock:
        mock.MODELS_DIR = "/tmp/models"
        mock.DATASET_DIR = "/tmp/dataset"
        yield mock

@pytest.fixture
def mock_logger():
    with patch("app.tasks.ai_tasks.logger") as mock:
        yield mock

def test_predict_task_file_not_found(mock_logger):
    """Test that predict_task raises FileNotFoundError if file is missing"""
    with patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            # Call .run to bypass Celery wrapper, passing None as self
            predict_task.run(None, "/non/existent/path.jpg")
        
        mock_logger.error.assert_called_with("File not found at path: /non/existent/path.jpg")

def test_predict_task_empty_file(mock_logger):
    """Test that predict_task raises ValueError if file is empty"""
    with patch("os.path.exists", return_value=True):
        with patch("os.path.getsize", return_value=0):
            with pytest.raises(ValueError):
                predict_task.run(None, "/path/to/empty.jpg")
                
            mock_logger.error.assert_called_with("File is empty: /path/to/empty.jpg")

@patch("app.services.ai_service.AIService.predict")
def test_predict_task_success(mock_predict, mock_logger):
    """Test successful prediction path"""
    mock_predict.return_value = (123, 0.95)
    
    with patch("os.path.exists", return_value=True):
        with patch("os.path.getsize", return_value=1024):
            with patch("os.remove") as mock_remove:
                result = predict_task.run(None, "/path/to/valid.jpg")
                
                assert result == {"product_id": 123, "confidence": 0.95}
                mock_remove.assert_called_once_with("/path/to/valid.jpg")

@patch("ultralytics.YOLO")
def test_get_model_gpu_selection(mock_yolo, mock_settings):
    """Test that correct model is selected based on GPU availability"""
    
    # reset singleton
    AIService._model = None
    
    with patch("torch.cuda.is_available", return_value=True):
        with patch("os.path.exists", return_value=True): # Model already exists
            AIService._get_model()
            # Should look for yolo11m-cls.pt
            assert "yolo11m-cls.pt" in mock_yolo.call_args[0][0]

    # reset singleton
    AIService._model = None
    
    with patch("torch.cuda.is_available", return_value=False):
        with patch("os.path.exists", return_value=True):
             AIService._get_model()
             # Should look for yolo11n-cls.pt
             assert "yolo11n-cls.pt" in mock_yolo.call_args[0][0]

