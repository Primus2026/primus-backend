import os
import asyncio
import aiofiles
import logging
import shutil
import tarfile
from datetime import datetime
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.storage import storage

logger = logging.getLogger("BACKUP_SERVICE")

class BackupService:
    # Inicjalizacja szyfratora - klucz musi być w Base64 (wygenerowany przez Fernet.generate_key())
    _cipher = Fernet(settings.BACKUP_ENCRYPTION_KEY.encode()) if settings.BACKUP_ENCRYPTION_KEY else None

    @staticmethod
    def _get_backup_filename() -> str:
        return f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"

    @staticmethod
    async def create_backup() -> str:
        """Tworzy pełny backup: DB dump + Media z MinIO, szyfruje i wysyła do MinIO."""
        archive_name = BackupService._get_backup_filename()
        tmp_dir = os.path.join("/tmp", archive_name.replace(".tar.gz", ""))
        archive_tmp_path = os.path.join("/tmp", archive_name)
        
        os.makedirs(tmp_dir, exist_ok=True)
        
        try:
            # 1. Zrzut bazy danych (PostgreSQL)
            sql_file = os.path.join(tmp_dir, "dump.sql")
            # Konwersja URL dla pg_dump (asyncpg -> postgresql)
            db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            
            logger.info("Starting database dump...")
            cmd = f"pg_dump '{db_url}' --format=custom --file='{sql_file}'"
            process = await asyncio.create_subprocess_shell(cmd, stderr=asyncio.subprocess.PIPE)
            _, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"pg_dump failed: {stderr.decode()}")

            # 2. Pobranie mediów z MinIO do folderu tymczasowego
            media_tmp_dir = os.path.join(tmp_dir, "media")
            prefixes = ["product_images", "reports", "datasets", "models"]
            
            for prefix in prefixes:
                logger.info(f"Downloading {prefix} for backup...")
                files = await storage.list(f"{prefix}/", recursive=True)
                for file_info in files:
                    storage_path = f"{prefix}/{file_info['name']}"
                    dest_path = os.path.join(media_tmp_dir, prefix, file_info['name'])
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    
                    content = await storage.get(storage_path)
                    async with aiofiles.open(dest_path, "wb") as f:
                        await f.write(content)

            # 3. Tworzenie archiwum TAR.GZ
            logger.info("Creating archive...")
            await asyncio.to_thread(BackupService._create_tar, archive_tmp_path, tmp_dir, media_tmp_dir)
            
            # 4. Szyfrowanie i wysyłka do bucketu 'backups'
            logger.info(f"Encrypting and uploading: backups/{archive_name}")
            async with aiofiles.open(archive_tmp_path, "rb") as f:
                raw_data = await f.read()
                encrypted_data = BackupService._cipher.encrypt(raw_data)
                await storage.save(f"backups/{archive_name}", encrypted_data)
                
            return archive_name
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise e
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
            if os.path.exists(archive_tmp_path):
                os.remove(archive_tmp_path)

    @staticmethod
    async def restore_backup(filename: str):
        """Pobiera backup, odszyfrowuje go i przywraca bazę oraz pliki."""
        tmp_dir = os.path.join("/tmp", f"restore_{filename.replace('.tar.gz', '')}")
        archive_tmp_path = os.path.join("/tmp", filename)
        
        try:
            # 1. Pobranie i odszyfrowanie
            logger.info(f"Fetching and decrypting {filename}...")
            encrypted_content = await storage.get(f"backups/{filename}")
            decrypted_content = BackupService._cipher.decrypt(encrypted_content)
            
            async with aiofiles.open(archive_tmp_path, "wb") as f:
                await f.write(decrypted_content)

            # 2. Rozpakowanie
            os.makedirs(tmp_dir, exist_ok=True)
            await asyncio.to_thread(BackupService._extract_tar, archive_tmp_path, tmp_dir)
            
            # 3. Przywracanie Bazy Danych
            sql_file = os.path.join(tmp_dir, "db", "dump.sql")
            if os.path.exists(sql_file):
                logger.info("Restoring database...")
                db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
                # --clean usuwa istniejące tabele przed odtworzeniem
                cmd = f"pg_restore --clean --if-exists --no-owner --dbname='{db_url}' '{sql_file}'"
                process = await asyncio.create_subprocess_shell(cmd, stderr=asyncio.subprocess.PIPE)
                _, stderr = await process.communicate()
                if process.returncode != 0:
                    logger.warning(f"pg_restore notice: {stderr.decode()}")

            # 4. Przywracanie Mediów do MinIO
            extracted_media = os.path.join(tmp_dir, "media")
            if os.path.exists(extracted_media):
                logger.info("Restoring media files to MinIO...")
                for root, _, files in os.walk(extracted_media):
                    for file in files:
                        full_path = os.path.join(root, file)
                        # Ścieżka relatywna do 'media', np. 'product_images/foto.jpg'
                        rel_path = os.path.relpath(full_path, extracted_media)
                        
                        async with aiofiles.open(full_path, "rb") as f:
                            content = await f.read()
                            await storage.save(rel_path, content)
            
            logger.info("Restore completed successfully.")
                
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise e
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
            if os.path.exists(archive_tmp_path):
                os.remove(archive_tmp_path)

    @staticmethod
    def _create_tar(archive_path: str, sql_dir: str, media_dir: str):
        with tarfile.open(archive_path, "w:gz") as tar:
            dump_path = os.path.join(sql_dir, "dump.sql")
            if os.path.exists(dump_path):
                tar.add(dump_path, arcname="db/dump.sql")
            if os.path.exists(media_dir):
                tar.add(media_dir, arcname="media")

    @staticmethod
    def _extract_tar(archive_path: str, extract_path: str):
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_path)

    @staticmethod
    async def list_backups() -> list[dict]:
        """Listuje backupy bezpośrednio z MinIO."""
        backups = await storage.list("backups/", recursive=True)
        for b in backups:
            b["source"] = "minio"
        backups.sort(key=lambda x: x['name'], reverse=True)
        return backups