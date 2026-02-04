import os
import tarfile
import subprocess
import logging
from datetime import datetime
from app.core.config import settings
import aiofiles
import asyncio
import shutil
from app.core.storage import storage

logger = logging.getLogger("BACKUP_SERVICE")

class BackupService:
    
    @staticmethod
    def _get_backup_filename() -> str:
        return f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @staticmethod
    async def create_backup() -> str:
        """
        Creates a full backup including PostgreSQL dump and media files (MinIO).
        Saves locally to persistent storage /app/backups.
        """
        base_name = BackupService._get_backup_filename()
        tmp_dir = os.path.join("/tmp", base_name)
        os.makedirs(tmp_dir, exist_ok=True)
        
        # Local Persistent Backup Dir
        local_backup_dir = "/app/backups"
        os.makedirs(local_backup_dir, exist_ok=True)
        
        try:
            # 1. Database Dump
            sql_file = os.path.join(tmp_dir, "dump.sql")
            db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            
            logger.info("Starting database dump...")
            
            # pg_dump command
            cmd = f"pg_dump '{db_url}' --format=custom --file='{sql_file}'"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"pg_dump failed: {stderr.decode()}")
            
            logger.info("Database dump completed.")

            # 2. Download Media from MinIO
            # Structure in archive: media/product_images/..., media/reports/...
            media_tmp_dir = os.path.join(tmp_dir, "media")
            os.makedirs(media_tmp_dir, exist_ok=True)

            prefixes_to_backup = ["product_images", "reports"]
            
            for prefix in prefixes_to_backup:
                logger.info(f"Backing up {prefix} from storage...")
                # Use prefix + "/" to ensure we map to the bucket root key prefix correctly
                files = await storage.list(f"{prefix}/", recursive=True)
                for file_info in files:
                    file_name = file_info['name'] # relative to prefix e.g. "image.jpg"
                    storage_path = f"{prefix}/{file_name}"
                    
                    # Destination path in tmp
                    dest_path = os.path.join(media_tmp_dir, prefix, file_name)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    
                    try:
                        content = await storage.get(storage_path)
                        async with aiofiles.open(dest_path, "wb") as f:
                            await f.write(content)
                    except Exception as e:
                         logger.warning(f"Failed to backup file {storage_path}: {e}")

            # 3. Create Archive
            archive_name = f"{base_name}.tar.gz"
            archive_path = os.path.join("/tmp", archive_name)
            
            logger.info("Creating archive...")
            
            # Run tar in a thread to not block event loop
            # Pass media_tmp_dir as the media directory to archive
            await asyncio.to_thread(BackupService._create_tar, archive_path, tmp_dir, media_tmp_dir)
            
            # 4. Save to Local Persistent Backup Dir
            final_path = os.path.join(local_backup_dir, archive_name)
            logger.info(f"Saving backup to persistent local storage: {final_path}")
            shutil.move(archive_path, final_path)
                
            return archive_name
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise e
        finally:
            # Cleanup
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
            if 'archive_path' in locals() and os.path.exists(archive_path):
                # Only try to remove if it wasn't moved
                if os.path.exists(archive_path):
                    os.remove(archive_path)

    @staticmethod
    def _create_tar(archive_path: str, sql_dir: str, media_dir: str):
        with tarfile.open(archive_path, "w:gz") as tar:
            # Add SQL dump - sql_dir is actually the tmp_dir containing dump.sql
            dump_path = os.path.join(sql_dir, "dump.sql")
            if os.path.exists(dump_path):
                tar.add(dump_path, arcname="db/dump.sql")
            
            # Add Media
            # We want the archive to contain media/product_images/...
            # media_dir contains product_images/ and reports/
            if os.path.exists(media_dir):
                 tar.add(media_dir, arcname="media")

    @staticmethod
    async def list_backups() -> list[dict]:
        """Lists available backups from local persistence."""
        backups = []
        local_backup_dir = "/app/backups"
        
        if os.path.exists(local_backup_dir):
            try:
                for filename in os.listdir(local_backup_dir):
                    if filename.endswith(".tar.gz"):
                         filepath = os.path.join(local_backup_dir, filename)
                         try:
                             stat = os.stat(filepath)
                             backups.append({
                                 "name": filename,
                                 "size": stat.st_size,
                                 "modified": stat.st_mtime,
                                 "source": "local" 
                             })
                         except OSError:
                             continue
            except Exception as e:
                logger.error(f"Failed to list local backups: {e}")

        backups.sort(key=lambda x: x['name'], reverse=True)
        return backups

    @staticmethod
    async def restore_backup(filename: str):
        """
        Restores backup from local storage.
        WARNING: This overwrites current data.
        """
        base_name = filename.replace(".tar.gz", "")
        tmp_dir = os.path.join("/tmp", f"restore_{base_name}")
        local_backup_path = os.path.join("/app/backups", filename)
        
        if not os.path.exists(local_backup_path):
             raise FileNotFoundError(f"Backup file not found: {filename}")

        os.makedirs(tmp_dir, exist_ok=True)
        
        try:
            # 1. Extract
            logger.info(f"Extracting {filename}...")
            await asyncio.to_thread(BackupService._extract_tar, local_backup_path, tmp_dir)
            
            # 2. Restore DB
            sql_file = os.path.join(tmp_dir, "db", "dump.sql")
            if not os.path.exists(sql_file):
                 raise Exception("Backup archive does not contain db/dump.sql")
            
            logger.info("Restoring database...")
            # Using pg_restore for custom format
            db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            cmd = f"pg_restore --clean --if-exists --no-owner --dbname='{db_url}' '{sql_file}'"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.warning(f"pg_restore finished with code {process.returncode}: {stderr.decode()}")
                
            logger.info("Database restoration completed.")
            
            # 3. Restore Media to MinIO
            extracted_media = os.path.join(tmp_dir, "media")
            if os.path.exists(extracted_media):
                logger.info("Restoring media files to storage...")
                
                # Walk through extracted media
                for root, dirs, files in os.walk(extracted_media):
                    for file in files:
                        full_path = os.path.join(root, file)
                        # Determine relative path from 'media' root
                        # extracted_media is .../media
                        # file is .../media/product_images/foo.jpg
                        # relative should be product_images/foo.jpg
                        
                        relative_path = os.path.relpath(full_path, extracted_media)
                        
                        # Upload to storage
                        # Using aiofiles to read
                        try:
                            async with aiofiles.open(full_path, "rb") as f:
                                content = await f.read()
                                await storage.save(relative_path, content)
                        except Exception as e:
                            logger.error(f"Failed to restore file {relative_path}: {e}")
                
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise e
        finally:
             if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)

    @staticmethod
    def _extract_tar(archive_path: str, extract_path: str):
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_path)
