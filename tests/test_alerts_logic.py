import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from app.schemas.alert import AlertType

@pytest.mark.asyncio
async def test_alert_duplication_logic_15_minutes(async_client: AsyncClient, db_session):
    # Initial time
    start_time = datetime.now()

    alert_payload = {
        "alert_type": AlertType.TEMP,
        "rack_id": 1,
        "product_id": None,
        "message": "High Temp",
        "last_valid_weight": 0.0,
        "position_row": 1,
        "position_col": 1
    }

    # Helper to post alert
    async def post_alert():
        return await async_client.post("/api/v1/alerts/", json=alert_payload)

    # 1. Create first alert at T=0
    with patch('app.services.alert_service.datetime') as mock_dt:
        mock_dt.now.return_value = start_time
        mock_dt.side_effect = lambda *args, **kw: datetime.now(*args, **kw)
        
        resp = await post_alert()
        assert resp.status_code == 201
        data1 = resp.json()
        alert_id_1 = data1["id"]
        assert data1["is_resolved"] is False

    # 2. Try duplicate immediately at T=0 (should be same alert)
    with patch('app.services.alert_service.datetime') as mock_dt:
        mock_dt.now.return_value = start_time
        
        resp = await post_alert()
        assert resp.status_code == 201
        data2 = resp.json()
        assert data2["id"] == alert_id_1

    # 3. Try duplicate at T+10m (should be same alert, < 15m)
    with patch('app.services.alert_service.datetime') as mock_dt:
        mock_dt.now.return_value = start_time + timedelta(minutes=10)
        
        resp = await post_alert()
        assert resp.status_code == 201
        data3 = resp.json()
        assert data3["id"] == alert_id_1

    # 4. Try duplicate at T+16m (should be NEW alert, > 15m)
    with patch('app.services.alert_service.datetime') as mock_dt:
        mock_dt.now.return_value = start_time + timedelta(minutes=16)
        
        resp = await post_alert()
        assert resp.status_code == 201
        data4 = resp.json()
        assert data4["id"] != alert_id_1
