

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.ai_service import AIService
from app.core.config import settings
import os
import tempfile
import shutil

@pytest.fixture(autouse=True)
def reset_ai_service():
    # Reset AI Service state
    AIService._model = None
    yield
    AIService._model = None

def test_get_model_priority_storage(mock_storage, mock_yolo, temp_models_dir):
    """
    Test that model is loaded from storage if available.
    """
    mock_storage.exists.return_value = True
    mock_storage.get.return_value = b"model_bytes"
    
    with patch("os.path.exists", return_value=True):
        with patch("aiofiles.open", new_callable=MagicMock) as mock_open:
            mock_file = AsyncMock()
            mock_open.return_value.__aenter__.return_value = mock_file
            
            model = AIService._get_model()
            
            mock_storage.exists.assert_called_with("models/best.pt")
            assert mock_yolo.called
            args = mock_yolo.call_args[0]
            assert "best.pt" in args[0]

def test_get_model_fallback_base(mock_storage, mock_yolo, temp_models_dir):
    """
    Test that if storage does not have best.pt, it falls back to base model.
    """
    mock_storage.exists.return_value = False
    
    with patch("os.path.exists", return_value=True): 
         model = AIService._get_model()
         
         mock_storage.exists.assert_called_with("models/best.pt")
         assert mock_yolo.called
         args = mock_yolo.call_args[0]
         assert "yolo11" in args[0]

def test_retrain_model_orchestration(mock_storage, mock_yolo, mock_redis, temp_models_dir):
    """
    Test the retraining flow: Download -> Train -> Upload
    """
    mock_storage.list.return_value = [{"name": "temp.txt"}] 
    
    with patch.object(AIService, "_download_dataset", return_value=True), \
         patch.object(AIService, "_prepare_split_dataset", return_value=True), \
         patch.object(AIService, "_get_model", return_value=MagicMock()) as mock_get_model, \
         patch("os.path.exists", return_value=True), \
         patch("aiofiles.open", new_callable=MagicMock) as mock_aio_open, \
         patch("shutil.rmtree") as mock_rmtree:
         
         mock_file = AsyncMock()
         mock_file.read.return_value = b"new_best_pt"
         mock_aio_open.return_value.__aenter__.return_value = mock_file
         
         AIService.retrain_model()
         
         mock_get_model.return_value.train.assert_called_once()
         
         save_calls = mock_storage.save.await_args_list
         
         uploaded = any("best.pt" in str(call.args[0]) for call in save_calls)
         assert uploaded, f"New model was not uploaded. Calls: {save_calls}"
         
         assert mock_storage.delete.called

