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
    summary="Rozpocznij generowanie raportu",
    responses={
        202: {"description": "Generowanie raportu rozpoczęte pomyślnie"},
        401: {"description": "Brak autoryzacji"},
        400: {"description": "Niepoprawny typ raportu"},
        501: {"description": "Raport temperatur nie zaimplementowany"}
    },
)
def generate_report(
    report_type: ReportType,
    filters: Optional[ReportFilter] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Uruchomienie generowania raportu.
    Zwraca identyfikator zadania (task_id) do śledzenia postępu.

    **report_type**:
    - **expiry**: Raport dat ważności.
    - **audit**: Pełny raport inwentaryzacyjny.
    - **temp**: Raport temperatur (planowane).

    Opcjonalne filtry (tylko dla raportów expiry i temp):
    - **rack_id**: Filtrowanie po konkretnym regale.
    - **barcode**: Filtrowanie po kodzie kreskowym produktu.
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
    Sprawdzenie statusu zadania generowania raportu.
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
    Lista dostępnych wygenerowanych raportów.
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
    Pobranie konkretnego pliku raportu.
    """
    from fastapi import Response
    content = await ReportStorageService.get_report_content(filename)
    # Stream the file
    return Response(
        content=content, 
        media_type='application/pdf',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

