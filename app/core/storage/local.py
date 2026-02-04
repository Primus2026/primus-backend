import os
import aiofiles
from typing import BinaryIO, Optional, Union
from pathlib import Path
from app.core.config import settings
from .base import StorageProvider
import logging

logger = logging.getLogger("LocalStorage")

class LocalStorageProvider(StorageProvider):
    def __init__(self):
        self.root = Path(settings.MEDIA_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, path: str, content: Union[bytes, BinaryIO, "UploadFile"], content_type: Optional[str] = None) -> str:
        full_path = self.root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        if isinstance(content, bytes):
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(content)
        elif hasattr(content, "read") and hasattr(content, "seek"):
            # Handle UploadFile (async) or standard file (sync)
            # Check for async read
            import asyncio
            is_async = asyncio.iscoroutinefunction(content.read)
            
            if is_async:
                await content.seek(0)
                data = await content.read()
            else:
                content.seek(0)
                data = content.read()
                
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(data)
        else:
             raise ValueError("Unsupported content type for upload")
             
        return path

    async def get(self, path: str) -> bytes:
        full_path = self.root / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str):
        full_path = self.root / path
        if full_path.exists():
            os.remove(full_path)

    def get_url(self, path: str) -> str:
        # Assumes StaticFiles is mounted at /media
        # Return absolute URL? Or relative?
        # Standard practice is usually relative "/media/..." or absolute "http://..."
        # Let's return relative starting with /media/
        return f"/media/{path}"

    async def exists(self, path: str) -> bool:
        full_path = self.root / path
        return full_path.exists()

    async def list(self, prefix: str, recursive: bool = False) -> list[dict]:
        results = []
        target_dir = self.root / prefix
        
        if not target_dir.exists():
            return []
            
        if recursive:
            for root, _, files in os.walk(target_dir):
                for file in files:
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(self.root)
                    stat = file_path.stat()
                    results.append({
                        "name": str(rel_path),
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
        else:
            for item in target_dir.iterdir():
                if item.is_file():
                    stat = item.stat()
                    results.append({
                        "name": item.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
        return results
