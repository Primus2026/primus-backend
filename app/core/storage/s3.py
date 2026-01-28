import asyncio
import aiobotocore.session
from typing import BinaryIO, Union, Optional
from app.core.config import settings
from .base import StorageProvider
import logging

logger = logging.getLogger("S3Storage")

class S3StorageProvider(StorageProvider):
    def __init__(self):
        self.session = aiobotocore.session.get_session()
        self.endpoint_url = f"http://{settings.MINIO_ENDPOINT}"
        self.access_key = settings.MINIO_ACCESS_KEY
        self.secret_key = settings.MINIO_SECRET_KEY
        self.bucket_name = "product-images" # Default bucket, dynamic switching handled in methods if needed
        self.secure = settings.MINIO_SECURE

    def _get_bucket_from_path(self, path: str) -> tuple[str, str]:
        parts = path.split('/', 1)
        if len(parts) > 1:
            prefix = parts[0]
            if prefix == "reports": return settings.BUCKET_REPORTS, parts[1]
            if prefix == "datasets": return settings.BUCKET_DATASETS, parts[1]
            if prefix == "models": return settings.BUCKET_MODELS, parts[1]
            if prefix == "product_images": return settings.BUCKET_IMAGES, parts[1]
        
        # Default fallback
        return settings.BUCKET_IMAGES, path


    async def save(self, path: str, content: Union[bytes, BinaryIO, "UploadFile"], content_type: Optional[str] = None) -> str:
        bucket, key = self._get_bucket_from_path(path)
        
        async with self.session.create_client(
            's3', 
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure
        ) as client:
            if isinstance(content, bytes):
                body = content
            elif hasattr(content, "read") and hasattr(content, "seek"):
                 # Handle UploadFile (async) vs standard file (sync)
                 # Check if seek/read are awaitable
                 if hasattr(content, "seek") and callable(content.seek) and asyncio.iscoroutinefunction(content.seek):
                     await content.seek(0)
                     body = await content.read()
                 else:
                     content.seek(0)
                     body = content.read()
            else:
                 raise ValueError("Unsupported content type for upload")
            
            await client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type or 'application/octet-stream')
        return path

    async def get(self, path: str) -> bytes:
        bucket, key = self._get_bucket_from_path(path)
        async with self.session.create_client(
            's3', 
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure
        ) as client:
            response = await client.get_object(Bucket=bucket, Key=key)
            async with response['Body'] as stream:
                return await stream.read()

    async def delete(self, path: str):
        bucket, key = self._get_bucket_from_path(path)
        async with self.session.create_client(
            's3', 
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure
        ) as client:
            await client.delete_object(Bucket=bucket, Key=key)

    def get_url(self, path: str) -> str:
        bucket, key = self._get_bucket_from_path(path)
        # Construct public URL using external endpoint
        base_url = settings.MINIO_EXTERNAL_ENDPOINT.rstrip('/')
        return f"{base_url}/{bucket}/{key}"

    async def exists(self, path: str) -> bool:
        bucket, key = self._get_bucket_from_path(path)
        async with self.session.create_client(
            's3', 
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure
        ) as client:
            try:
                await client.head_object(Bucket=bucket, Key=key)
                return True
            except:
                return False


    async def list(self, prefix: str, recursive: bool = False) -> list[dict]:
        bucket, key_prefix = self._get_bucket_from_path(prefix)
        # S3 list_objects_v2
        async with self.session.create_client(
            's3', 
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure
        ) as client:
            paginator = client.get_paginator('list_objects_v2')
            args = {"Bucket": bucket, "Prefix": key_prefix}
            if not recursive:
                args["Delimiter"] = "/"
            
            results = []
            async for page in paginator.paginate(**args):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # logic to determine name
                    # If prefix was "datasets/", key is "datasets/1/a.jpg".
                    # We want "1/a.jpg" if recursive?
                    # Local provider implementation returns relative to prefix path.
                    # if key starts with key_prefix, strip it.
                    if key.startswith(key_prefix):
                         name = key[len(key_prefix):]
                         if name.startswith("/"): name = name[1:]
                    else:
                         name = key
                    
                    if not name: continue # Skip directory placeholder itself if it matches prefix exactly

                    results.append({
                        "name": name,
                        "size": obj['Size'],
                        "modified": obj['LastModified'].timestamp()
                    })
            return results

