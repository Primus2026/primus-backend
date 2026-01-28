from functools import lru_cache
from app.core.config import settings
from .base import StorageProvider
from .s3 import S3StorageProvider

@lru_cache()
def get_storage() -> StorageProvider:
    return S3StorageProvider()



# Global instance for easy import
storage = get_storage()
