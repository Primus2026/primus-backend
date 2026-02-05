import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.voice_service import VoiceService
from app.core.config import settings

@pytest.mark.asyncio
async def test_process_command_ollama_success():
    """Test VoiceService.process_command with Ollama provider."""
    mock_response = {
        "response": json.dumps({
            "action": "report_generate",
            "parameters": {"type": "inventory"}
        })
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = mock_response
        mock_post.return_value = mock_res
        
        with patch("app.core.config.settings.VOICE_LLM_PROVIDER", "ollama"), \
             patch("app.tasks.report_tasks.generate_inventory_report.delay") as mock_delay:
            
            mock_delay.return_value.id = "test-task-id"
            
            result = await VoiceService.process_command("Pokaż stan magazynu")
            
            assert result["status"] == "success"
            assert "inwentaryzacji" in result["message"]
            assert result["task_id"] == "test-task-id"
            mock_delay.assert_called_once()

@pytest.mark.asyncio
async def test_process_command_inbound_intent():
    """Test intent extraction for inbound process."""
    mock_response = {
        "response": json.dumps({
            "action": "process_inbound",
            "parameters": {"product_name": "Mleko 3.2%", "barcode": "123456", "quantity": 10}
        })
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = mock_response
        mock_post.return_value = mock_res
        
        with patch("app.core.config.settings.VOICE_LLM_PROVIDER", "ollama"):
            result = await VoiceService.process_command("Przyjmij 10 sztuk mleka")
            
            assert result["status"] == "success"
            assert "przyjęcia" in result["message"]
            assert result["action"] == "navigate_inbound"
            assert result["data"]["product_name"] == "Mleko 3.2%"
            assert result["data"]["quantity"] == 10

@pytest.mark.asyncio
async def test_process_command_unknown_intent():
    """Test behavior for unknown commands."""
    mock_response = {
        "response": json.dumps({
            "action": "unknown",
            "parameters": {}
        })
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = mock_response
        mock_post.return_value = mock_res
        
        with patch("app.core.config.settings.VOICE_LLM_PROVIDER", "ollama"):
            result = await VoiceService.process_command("Zrób mi kawę")
            
            assert result["status"] == "error"
            assert "Nie zrozumiałem" in result["message"]

@pytest.mark.asyncio
async def test_process_with_db_context():
    """Test that db context is correctly passed to system prompt."""
    mock_db = AsyncMock()
    mock_product = MagicMock()
    mock_product.name = "Test Product"
    mock_product.barcode = "999888"
    
    # Mock db result
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [mock_product]
    mock_db.execute.return_value = mock_execute_result
    
    mock_response = {
        "response": json.dumps({"action": "unknown", "parameters": {}})
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        
        with patch.object(VoiceService, "get_system_prompt", return_value="prompt") as mock_prompt_gen:
            await VoiceService.process_command("test", db=mock_db)
            
            # Verify database was queried
            mock_db.execute.assert_called_once()
            # Verify prompt generation received product info
            assert "Test Product" in mock_prompt_gen.call_args[0][0]
            assert "999888" in mock_prompt_gen.call_args[0][0]
