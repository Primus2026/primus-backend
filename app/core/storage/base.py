from abc import ABC, abstractmethod
from typing import BinaryIO, Optional, Union
from pathlib import Path

class StorageProvider(ABC):
    @abstractmethod
    async def save(self, path: str, content: Union[bytes, BinaryIO], content_type: Optional[str] = None) -> str:
        """
        Save content to the storage at the given path.
        Returns the path or key where the file is stored.
        """
        pass

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """
        Retrieve content from storage.
        """
        pass

    @abstractmethod
    async def delete(self, path: str):
        """
        Delete file from storage.
        """
        pass

    @abstractmethod
    def get_url(self, path: str) -> str:
        """
        Get public or presigned URL for the file.
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if file exists.
        """
        pass

    @abstractmethod
    async def list(self, prefix: str, recursive: bool = False) -> list[dict]:
        """
        List files with prefix. Returns list of dicts with 'name', 'size', 'modified'.
        If recursive=True, listing includes subdirectories (and 'name' includes relative path).
        """
        pass

