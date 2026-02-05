from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from celery.result import AsyncResult

from app.core.deps import get_current_user
from app.database.models.user import User
from app.schemas.report import ReportResponse, ReportGenerateResponse, ReportStatusResponse, ReportFilter
from app.services.report_storage import ReportStorageService
from app.tasks.report_tasks import generate_expiry_report_task
from app.schemas.report import ReportType

router = APIRouter()

@router.post(
    "/generate/{report_type}",
    response_model=ReportGenerateResponse,
    status_code=202,
    summary="Trigger Report Generation",
    responses={
        202: {"description": "Report generation initiated successfully"},
        401: {"description": "Not authenticated"},
        400: {"description": "Invalid report type"},
        501: {"description": "Temperature report not implemented yet"}
    },
)
def generate_report(
    report_type: ReportType,
    filters: Optional[ReportFilter] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Trigger generation of a report.
    Returns a task_id to poll for status.

    **report_type**:
    - **expiry**: Expiry date report.
    - **audit**: Full warehouse audit report.
    - **temp**: Temperature report (TO-DO).

    Optional filters (only for expiry and temp report):
    - **rack_id**: Filter by specific rack.
    - **barcode**: Filter by product barcode.
    """
    
    rack_id = filters.rack_id if filters else None
    barcode = filters.barcode if filters else None

    if report_type == ReportType.EXPIRY:
        task = generate_expiry_report_task.delay(rack_id=rack_id, barcode=barcode)
    elif report_type == ReportType.AUDIT:
        from app.tasks.report_tasks import generate_audit_report_task
        task = generate_audit_report_task.delay()
    elif report_type == ReportType.TEMP:
        from app.tasks.report_tasks import generate_temp_report_task
        task = generate_temp_report_task.delay(rack_id=rack_id, barcode=barcode)
    else:
        raise HTTPException(status_code=400, detail="Invalid report type.")
    
    return ReportGenerateResponse(
        task_id=task.id,
        message="Report generation initiated."
    )


@router.get(
    "/status/{task_id}",
    response_model=ReportStatusResponse,
    summary="Check Report Status",
    responses={
        200: {"description": "Status retrieved successfully"},
        401: {"description": "Not authenticated"},
        404: {"description": "Task not found"},
    },
)
def get_report_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Check the status of a report task.
    """
    task_result = AsyncResult(task_id)
    
    response = ReportStatusResponse(
        task_id=task_id,
        status=task_result.status
    )

    if task_result.successful():
        result = task_result.result
        # Result should be {"filename": "..."}
        if result and "filename" in result:
             response.result = result
             # Use secure API URL
             response.download_url = f"/api/v1/reports/download/{result['filename']}"
    elif task_result.failed():
        response.error = str(task_result.result)

    return response

@router.get(
    "/",
    response_model=List[ReportResponse],
    summary="List Reports",
    responses={
        200: {"description": "List of reports retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_reports(
    type_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    List available reports in storage.
    """
    return await ReportStorageService.list_reports(type_filter)

@router.get(
    "/download/{filename}",
    summary="Download Report",
    responses={
        200: {"description": "File stream"},
        401: {"description": "Not authenticated"},
        404: {"description": "Report not found"},
    },
)
async def download_report(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    Download a specific report file.
    """
    from fastapi import Response
    content = await ReportStorageService.get_report_content(filename)
    # Stream the file
    return Response(
        content=content, 
        media_type='application/pdf',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

