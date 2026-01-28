
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.storage.s3 import S3StorageProvider
from app.core.config import settings



def test_bucket_mapping(s3_provider):
    """Verify paths are mapped to correct buckets"""
    
    # Reports
    bucket, key = s3_provider._get_bucket_from_path("reports/test.pdf")
    assert bucket == settings.BUCKET_REPORTS
    assert key == "test.pdf"
    
    # Datasets
    bucket, key = s3_provider._get_bucket_from_path("datasets/1/img.jpg")
    assert bucket == settings.BUCKET_DATASETS
    assert key == "1/img.jpg"
    
    # Models
    bucket, key = s3_provider._get_bucket_from_path("models/best.pt")
    assert bucket == settings.BUCKET_MODELS
    assert key == "best.pt"
    
    # Default (Product Images)
    bucket, key = s3_provider._get_bucket_from_path("product_images/abc.jpg")
    assert bucket == settings.BUCKET_IMAGES
    assert key == "abc.jpg"
    
    # Fallback
    bucket, key = s3_provider._get_bucket_from_path("unknown/file.txt")
    assert bucket == settings.BUCKET_IMAGES
    assert key == "unknown/file.txt"

def test_get_url(s3_provider):
    """Verify URL generation"""
    settings.MINIO_EXTERNAL_ENDPOINT = "http://localhost:9000"
    
    url = s3_provider.get_url("reports/test.pdf")
    # bucket is reports
    expected = f"http://localhost:9000/{settings.BUCKET_REPORTS}/test.pdf"
    assert url == expected

@pytest.mark.asyncio
async def test_save_file():
    """Verify save calls put_object correctly"""
    with patch("aiobotocore.session.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        mock_client = AsyncMock()
        mock_session.create_client.return_value.__aenter__.return_value = mock_client
        
        provider = S3StorageProvider()
        
        await provider.save("reports/test.pdf", b"data")
        
        mock_client.put_object.assert_awaited_with(
            Bucket=settings.BUCKET_REPORTS,
            Key="test.pdf",
            Body=b"data",
            ContentType='application/octet-stream'
        )

@pytest.mark.asyncio
async def test_list_files():
    """Verify list functionality and recursive logic"""
    with patch("aiobotocore.session.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        
        mock_client = MagicMock() 
        
        mock_ctx = AsyncMock()
        mock_session.create_client.return_value = mock_ctx
        
        mock_client_instance = MagicMock() 
        mock_ctx.__aenter__.return_value = mock_client_instance
        

        mock_paginator = MagicMock()
        mock_client_instance.get_paginator.return_value = mock_paginator
        
        # Async Iterator for paginate
        async def async_pages(**kwargs):
            yield {
                "Contents": [
                    {"Key": "1/a.jpg", "Size": 100, "LastModified": MagicMock(timestamp=lambda: 123)},
                    {"Key": "1/b.jpg", "Size": 200, "LastModified": MagicMock(timestamp=lambda: 123)}
                ]
            }
        
        mock_paginator.paginate.side_effect = async_pages
        
        provider = S3StorageProvider()
        results = await provider.list("datasets/", recursive=True)
        
        assert len(results) == 2
        assert results[0]["name"] == "1/a.jpg" 
        assert results[1]["name"] == "1/b.jpg"
