import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_process_voice_command_api(authorized_warehouseman_client):
    """Test the POST /api/v1/voice/ endpoint."""
    mock_result = {
        "status": "success",
        "message": "Report started",
        "task_id": "test-task-123"
    }
    
    with patch("app.services.voice_service.VoiceService.process_command", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = mock_result
        
        response = await authorized_warehouseman_client.post(
            "/api/v1/voice-command/",
            json={"text": "generate inventory report"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["task_id"] == "test-task-123"
        mock_process.assert_called_once()

@pytest.mark.asyncio
async def test_process_voice_command_empty_text(authorized_warehouseman_client):
    """Test API behavior with empty input."""
    response = await authorized_warehouseman_client.post(
        "/api/v1/voice-command/",
        json={"text": ""}
    )
    
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]

@pytest.mark.asyncio
async def test_process_voice_command_unauthorized(async_client):
    """Test that voice API requires authentication."""
    
    with patch("app.services.voice_service.VoiceService.process_command", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = {"status": "success"}
        response = await async_client.post(
            "/api/v1/voice-command/",
            json={"text": "hello"}
        )
        
        assert response.status_code == 200
