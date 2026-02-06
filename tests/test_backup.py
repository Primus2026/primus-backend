import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from app.services.backup_service import BackupService
from app.core.config import settings
import asyncio
import os

@pytest.mark.asyncio
async def test_create_backup_flow():
    """
    Test the create_backup method ensuring it calls postgres dump, tar, and upload.
    """
    # Mock dependencies
    with patch("asyncio.create_subprocess_shell") as mock_subprocess, \
         patch("app.core.storage.storage.save", new_callable=AsyncMock) as mock_storage_save, \
         patch("app.core.storage.storage.list", new_callable=AsyncMock) as mock_storage_list, \
         patch("app.core.storage.storage.get", new_callable=AsyncMock) as mock_storage_get, \
         patch("aiofiles.open", new_callable=MagicMock) as mock_aio_open, \
         patch("app.services.backup_service.BackupService._create_tar") as mock_create_tar, \
         patch("os.remove") as mock_remove, \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("os.makedirs") as mock_makedirs, \
         patch("shutil.move") as mock_move, \
         patch("os.path.exists", return_value=True):
        
        # Setup mock subprocess for pg_dump
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process
        
        # Setup mock file reading
        mock_file_handle = AsyncMock()
        mock_file_handle.read.return_value = b"archive_content"
        mock_aio_open.return_value.__aenter__.return_value = mock_file_handle

        # Mock storage list to return some files
        mock_storage_list.return_value = [{"name": "image.jpg"}]
        mock_storage_get.return_value = b"image_content"

        # ACT
        filename = await BackupService.create_backup()
        
        # ASSERT
        # 1. Check pg_dump called
        mock_subprocess.assert_called()
        cmd_arg = mock_subprocess.call_args[0][0]
        assert "pg_dump" in cmd_arg
        
        # 2. Check Tar creation
        mock_create_tar.assert_called()
        
        # 3. Check Storage Interactions
        # Should have listed files
        assert mock_storage_list.called
        # Should have downloaded files (check get called)
        assert mock_storage_get.called
        
        # 4. Check Cleanup
        mock_rmtree.assert_called()
        assert filename.startswith("backup_")
        assert filename.endswith(".tar.gz")

@pytest.mark.asyncio
async def test_restore_backup_flow():
    """
    Test the restore_backup flow.
    """
    filename = "backup_test.tar.gz"
    
    with patch("app.core.storage.storage.save", new_callable=AsyncMock) as mock_storage_save, \
         patch("app.core.storage.storage.get", new_callable=AsyncMock) as mock_storage_get, \
         patch("aiofiles.open", new_callable=MagicMock) as mock_aio_open, \
         patch("app.services.backup_service.BackupService._extract_tar") as mock_extract_tar, \
         patch("asyncio.create_subprocess_shell") as mock_subprocess, \
         patch("shutil.copytree") as mock_copytree, \
         patch("os.path.exists") as mock_exists, \
         patch("os.walk") as mock_walk, \
         patch("shutil.rmtree"), patch("os.makedirs"), patch("os.remove"):

        # Mocks
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process
        
        # Mock file write
        mock_file_handle = AsyncMock()
        mock_file_handle.read.return_value = b"content"
        mock_aio_open.return_value.__aenter__.return_value = mock_file_handle
        
        # Mock storage.get to return encrypted content
        mock_storage_get.return_value = BackupService._cipher.encrypt(b"test_content") if BackupService._cipher else b"test_content"

        # Mock os.walk to verify media restoration logic
        # root, dirs, files
        mock_walk.return_value = [
            ("/tmp/restore_x/media/product_images", [], ["test.jpg"])
        ]

        # ACT
        await BackupService.restore_backup(filename)
        
        # ASSERT
        # 1. Extract
        mock_extract_tar.assert_called()
        
        # 2. Restore DB (pg_restore)
        mock_subprocess.assert_called()
        cmd_arg = mock_subprocess.call_args[0][0]
        assert "pg_restore" in cmd_arg
        
        # 3. Restore Media (Upload to storage)
        mock_storage_save.assert_called()
        args = mock_storage_save.call_args[0]
        # Should upload product_images/test.jpg
        # Since we mocked os.walk return, the relative path derivation logic implies:
        # full_path = /tmp/restore_x/media/product_images/test.jpg
        # extracted_media = /tmp/restore_x/media
        # relpath = product_images/test.jpg
        assert "product_images/test.jpg" in str(args)
