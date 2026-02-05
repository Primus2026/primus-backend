from datetime import datetime
from typing import List, Dict, Optional
from fastapi import HTTPException
from app.core.config import settings
from app.core.storage import storage

class ReportStorageService:
    @staticmethod
    def _validate_filename(filename: str) -> str:
        """
        Validates the filename to prevent directory traversal.
        Returns the relative path key for storage.
        """
        if ".." in filename or "/" in filename or "\\" in filename:
             raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku")
        
        # Reports are stored under "reports" logical prefix
        return f"reports/{filename}"

    @classmethod
    async def list_reports(cls, type_filter: Optional[str] = None) -> List[Dict]:
        """
        Lists all reports in the storage.
        Optional filter by filename prefix/type.
        """
        # List files in "reports/"
        files = await storage.list("reports/")
        
        reports = []
        for file_info in files:
            filename = file_info["name"]
            if not filename.endswith(".pdf"):
                continue
            
            if type_filter and not filename.startswith(type_filter):
                continue
                
            reports.append({
                "filename": filename,
                "created_at": datetime.fromtimestamp(file_info["modified"]),
                "size_bytes": file_info["size"]
            })
        
        # Sort by creation time desc
        reports.sort(key=lambda x: x["created_at"], reverse=True)
        return reports

    @classmethod
    async def get_report_content(cls, filename: str) -> bytes:
        """Returns the content of a report if it exists, else raises 404."""
        path = cls._validate_filename(filename)
        try:
            return await storage.get(path)
        except Exception:
            raise HTTPException(status_code=404, detail="Raport nie został znaleziony")

    @classmethod
    async def save_report(cls, filename: str, content: bytes) -> str:
        """Saves content to a file. Returns the filename."""
        path = cls._validate_filename(filename)
        await storage.save(path, content)
        return filename

    @classmethod
    async def delete_report(cls, filename: str) -> bool:
        """Deletes a report."""
        try:
            path = cls._validate_filename(filename)
            await storage.delete(path)
            return True
        except Exception:
            pass 
        return False
    
    @classmethod
    async def cleanup_old_reports(cls, days: int = 7) -> int:
        """Deletes reports older than N days."""
        files = await storage.list("reports/")
        now = datetime.now()
        count = 0
        
        for file_info in files:
            filename = file_info["name"]
            if not filename.endswith(".pdf"):
                continue
            
            file_time = datetime.fromtimestamp(file_info["modified"])
            if (now - file_time).days > days:
                try:
                    await storage.delete(f"reports/{filename}")
                    count += 1
                except Exception:
                    pass
        return count
