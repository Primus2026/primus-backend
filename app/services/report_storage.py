import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import HTTPException

from app.core.config import settings

class ReportStorageService:
    # Use path from settings
    REPORT_DIR = Path(settings.REPORT_DIR)

    @classmethod
    def ensure_directory(cls):
        """Ensure the reports directory exists."""
        cls.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_path(filename: str) -> Path:
        """
        Validates the filename to prevent directory traversal.
        Returns the absolute path if valid.
        """
        ReportStorageService.ensure_directory()
        
        if ".." in filename or "/" in filename or "\\" in filename:
             raise HTTPException(status_code=400, detail="Invalid filename")

        target_path = (ReportStorageService.REPORT_DIR / filename).resolve()
        
        # Security check: Ensure the resolved path is still within REPORT_DIR
        # This handles symlink attacks etc, though redundant with the string check above
        if not str(target_path).startswith(str(ReportStorageService.REPORT_DIR.resolve())):
             raise HTTPException(status_code=400, detail="Access denied")
             
        return target_path

    @classmethod
    def list_reports(cls, type_filter: Optional[str] = None) -> List[Dict]:
        """
        Lists all reports in the directory.
        Optional filter by filename prefix/type.
        """
        cls.ensure_directory()
        reports = []
        
        # Filename convention: TYPE_TIMESTAMP_ID.pdf
        # Example: EXPIRY_20260115_abc123.pdf
        
        for file in cls.REPORT_DIR.iterdir():
            if file.is_file() and file.suffix == ".pdf":
                if type_filter and not file.name.startswith(type_filter):
                    continue
                    
                stats = file.stat()
                reports.append({
                    "filename": file.name,
                    "created_at": datetime.fromtimestamp(stats.st_ctime),
                    "size_bytes": stats.st_size
                })
        
        # Sort by creation time desc
        reports.sort(key=lambda x: x["created_at"], reverse=True)
        return reports

    @classmethod
    def get_report_path(cls, filename: str) -> Path:
        """Returns the path to a report if it exists, else raises 404."""
        path = cls._validate_path(filename)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        return path

    @classmethod
    def save_report(cls, filename: str, content: bytes) -> str:
        """Saves content to a file. Returns the filename."""
        path = cls._validate_path(filename)
        with open(path, "wb") as f:
            f.write(content)
        return filename

    @classmethod
    def delete_report(cls, filename: str) -> bool:
        """Deletes a report."""
        try:
            path = cls._validate_path(filename)
            if path.exists():
                os.remove(path)
                return True
        except Exception:
            pass # Fail silently or log
        return False
    
    @classmethod
    def cleanup_old_reports(cls, days: int = 7):
        """Deletes reports older than N days."""
        cls.ensure_directory()
        now = datetime.now()
        count = 0
        for file in cls.REPORT_DIR.iterdir():
            if file.is_file() and file.suffix == ".pdf":
                stats = file.stat()
                file_time = datetime.fromtimestamp(stats.st_ctime)
                if (now - file_time).days > days:
                    try:
                        os.remove(file)
                        count += 1
                    except OSError:
                        pass
        return count
