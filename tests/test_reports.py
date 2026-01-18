import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime, timedelta
from httpx import AsyncClient

from app.services.report_service import ReportService
from app.services.report_storage import ReportStorageService
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from app.database.models.rack import Rack
from app.database.models.alert import Alert, AlertType
from app.database.models.user import User
from app.core.config import settings

# ==========================================
# SERVICE LAYER TESTS
# ==========================================

def test_generate_expiry_pdf_creation(tmp_path):
    """
    Verifies that generate_expiry_pdf creates a file with a PDF header.
    """
    # 1. Setup Mock Data
    items = []
    
    # Mock Item
    p1 = MagicMock(spec=ProductDefinition)
    p1.name = "Test Product"
    p1.barcode = "123456789"
    
    item1 = MagicMock(spec=StockItem)
    item1.product = p1
    item1.rack = MagicMock(spec=Rack)
    item1.rack.label = "R-TEST"
    item1.expiry_date = datetime.now().date() + timedelta(days=5)
    item1.position_row = 1
    item1.position_col = 1
    items.append(item1)
    
    # 2. Define Output Path
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    filename = "TEST_REPORT.pdf"
    file_path = output_dir / filename
    
    # 3. Call Service
    generated_name = ReportService.generate_expiry_pdf(items, file_path)
    
    # 4. Assertions
    assert generated_name == filename
    assert file_path.exists()
    assert file_path.stat().st_size > 0
    
    # Check PDF Header using first bytes
    with open(file_path, "rb") as f:
        header = f.read(4)
        assert header == b"%PDF"

def test_report_storage_validate_path(tmp_path):
    """
    Verifies that ReportStorageService correctly validates paths 
    and prevents traversal.
    """
    # Patch REPORT_DIR
    mock_report_dir = tmp_path / "reports"
    mock_report_dir.mkdir()
    ReportStorageService.REPORT_DIR = mock_report_dir
    
    # Ensure dir exists
    ReportStorageService.ensure_directory()
    base_dir = ReportStorageService.REPORT_DIR
    
    # Valid
    valid_path = ReportStorageService._validate_path("test.pdf")
    assert valid_path == (base_dir / "test.pdf").resolve()
    
    # Traversal Attempt
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        ReportStorageService._validate_path("../secret.txt")
    assert excinfo.value.status_code == 400
    
    # Slash Attempt
    with pytest.raises(HTTPException):
        ReportStorageService._validate_path("sub/folder.pdf")

def test_report_storage_list_reports(tmp_path):
    """
    Verifies listing reports (Service Layer).
    """
    # Patch REPORT_DIR
    mock_report_dir = tmp_path / "reports_list"
    mock_report_dir.mkdir()
    ReportStorageService.REPORT_DIR = mock_report_dir
    
    # Create dummy files
    (mock_report_dir / "EXPIRY_1.pdf").touch()
    (mock_report_dir / "EXPIRY_2.pdf").touch()
    (mock_report_dir / "OTHER.txt").touch() # Should be ignored
    
    reports = ReportStorageService.list_reports()
    
    assert len(reports) == 2
    filenames = [r["filename"] for r in reports]
    assert "EXPIRY_1.pdf" in filenames
    assert "EXPIRY_2.pdf" in filenames
    assert "OTHER.txt" not in filenames


# ==========================================
# API ENDPOINT TESTS
# ==========================================

@pytest.mark.asyncio
async def test_generate_expiry_report_endpoint(authorized_warehouseman_client: AsyncClient):
    """
    Test POST /reports/generate?report_type=expiry
    Mocks the Celery task delay method.
    """
    with patch("app.api.v1.endpoints.reports.generate_expiry_report_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        mock_delay.return_value = mock_task

        response = await authorized_warehouseman_client.post("/api/v1/reports/generate/expiry")
        
        assert response.status_code == 202
        assert response.json()["task_id"] == "test-task-id"
        # Verify called with default None for filters
        mock_delay.assert_called_once_with(rack_id=None, barcode=None)

@pytest.mark.asyncio
async def test_generate_expiry_report_with_filters(authorized_warehouseman_client: AsyncClient):
    """
    Test POST /reports/generate?report_type=expiry with filters
    """
    with patch("app.api.v1.endpoints.reports.generate_expiry_report_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "test-task-id-filtered"
        mock_delay.return_value = mock_task

        payload = {"rack_id": 5, "barcode": "ABC-123"}
        response = await authorized_warehouseman_client.post("/api/v1/reports/generate/expiry", json=payload)
        
        assert response.status_code == 202
        assert response.json()["task_id"] == "test-task-id-filtered"
        
        # Verify filters passed to task
        mock_delay.assert_called_once_with(rack_id=5, barcode="ABC-123")

@pytest.mark.asyncio
async def test_get_report_status_endpoint_success(authorized_warehouseman_client: AsyncClient):
    """
    Test GET /reports/expiry/status/{task_id} - Success case
    Mocks AsyncResult to return success.
    """
    with patch("app.api.v1.endpoints.reports.AsyncResult") as mock_async_result:
        mock_result_instance = MagicMock()
        mock_result_instance.status = "SUCCESS"
        mock_result_instance.successful.return_value = True
        mock_result_instance.result = {"filename": "test_report.pdf"}
        
        mock_async_result.return_value = mock_result_instance

        response = await authorized_warehouseman_client.get("/api/v1/reports/status/test-task-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["result"]["filename"] == "test_report.pdf"
        assert data["download_url"] == "/api/v1/reports/download/test_report.pdf"

@pytest.mark.asyncio
async def test_get_report_status_endpoint_pending(authorized_warehouseman_client: AsyncClient):
    """
    Test GET /reports/expiry/status/{task_id} - Pending case
    """
    with patch("app.api.v1.endpoints.reports.AsyncResult") as mock_async_result:
        mock_result_instance = MagicMock()
        mock_result_instance.status = "PENDING"
        mock_result_instance.successful.return_value = False
        mock_result_instance.failed.return_value = False
        
        mock_async_result.return_value = mock_result_instance

        response = await authorized_warehouseman_client.get("/api/v1/reports/status/test-task-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING"
        assert "download_url" not in data or data["download_url"] is None

@pytest.mark.asyncio
async def test_list_reports_endpoint(authorized_warehouseman_client: AsyncClient):
    """
    Test GET /reports/
    Mocks ReportStorageService.list_reports
    """
    from datetime import datetime
    mock_reports = [
        {"filename": "report1.pdf", "created_at": datetime(2023, 1, 1), "size_bytes": 1024},
        {"filename": "report2.pdf", "created_at": datetime(2023, 1, 2), "size_bytes": 2048}
    ]
    
    with patch("app.services.report_storage.ReportStorageService.list_reports", return_value=mock_reports):
        response = await authorized_warehouseman_client.get("/api/v1/reports/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["filename"] == "report1.pdf"

@pytest.mark.asyncio
async def test_download_report_endpoint(authorized_warehouseman_client: AsyncClient, tmp_path):
    """
    Test GET /reports/download/{filename}
    Creates a dummy file and mocks get_report_path.
    """
    # Create a dummy report file to stream
    dummy_file = tmp_path / "dummy_report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4 dummy content")
    
    with patch("app.services.report_storage.ReportStorageService.get_report_path", return_value=dummy_file):
        response = await authorized_warehouseman_client.get("/api/v1/reports/download/dummy_report.pdf")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

def test_generate_audit_pdf_creation(tmp_path):
    """
    Verifies that generate_audit_pdf creates a file with a PDF header and handles all sections.
    """
    # 1. Setup Mock Data
    
    # Mock Racks
    rack1 = MagicMock(spec=Rack)
    rack1.designation = "R-01"
    rack1.rows_m = 5
    rack1.cols_n = 10
    # Mock items list for fill calculation
    rack1.items = [1, 2, 3] # just need length
    
    rack2 = MagicMock(spec=Rack)
    rack2.designation = "R-02"
    rack2.rows_m = 4
    rack2.cols_n = 5
    rack2.items = [] # empty
    
    racks = [rack1, rack2]
    
    # Mock Items
    p1 = MagicMock(spec=ProductDefinition)
    p1.name = "Test Product A"
    p1.barcode = "123"
    
    u1 = MagicMock(spec=User)
    u1.email = "warehouseman@example.com"
    
    item1 = MagicMock(spec=StockItem)
    item1.product = p1
    item1.rack = rack1
    item1.position_row = 1
    item1.position_col = 1
    item1.entry_date = datetime.now()
    item1.receiver = u1
    
    items = [item1]
    
    # Mock Alerts
    alert1 = MagicMock(spec=Alert)
    alert1.created_at = datetime.now()
    alert1.alert_type = AlertType.TEMP
    alert1.message = "Temperature too high"
    alert1.rack = rack1
    alert1.product = None
    
    alert2 = MagicMock(spec=Alert)
    alert2.created_at = datetime.now() - timedelta(days=1)
    alert2.alert_type = AlertType.EXPIRY
    alert2.message = "Product expired"
    alert2.rack = None
    alert2.product = p1
    
    alerts = [alert1, alert2]
    
    # 2. Define Output Path
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    filename = "AUDIT_TEST.pdf"
    file_path = output_dir / filename
    
    # 3. Call Service
    generated_name = ReportService.generate_audit_pdf(racks, items, alerts, file_path)
    
    # 4. Assertions
    assert generated_name == filename
    assert file_path.exists()
    assert file_path.stat().st_size > 0
    
    # Check PDF Header using first bytes
    with open(file_path, "rb") as f:
        header = f.read(4)
        assert header == b"%PDF"

def test_generate_audit_pdf_empty(tmp_path):
    """
    Verifies that generate_audit_pdf handles empty lists gracefully.
    """
    output_dir = tmp_path / "reports_empty"
    output_dir.mkdir()
    file_path = output_dir / "AUDIT_EMPTY.pdf"
    
    ReportService.generate_audit_pdf([], [], [], file_path)
    
    assert file_path.exists()
    assert file_path.stat().st_size > 0

