import os
import shutil
from app.core.config import settings
import logging
import uuid
import random
from typing import List
from fastapi import UploadFile, HTTPException
from app.core.redis_client import RedisClient
from app.core.storage import storage
import aiofiles
import asyncio

logger = logging.getLogger("AI_Service")


class AIService:
    _model = None

    @classmethod
    def _get_model(cls):
        """Loads the model once and caches it."""
        if cls._model is None:
            from ultralytics import YOLO
            import torch

            # Check for custom fine-tuned model first
            custom_model_local_path = os.path.join(settings.MODELS_DIR, "best.pt")
            os.makedirs(settings.MODELS_DIR, exist_ok=True)
            
            # Helper to check storage and download
            async def check_and_download_model():
                if await storage.exists("models/best.pt"):
                     logger.info("Found best.pt in storage. Downloading...")
                     content = await storage.get("models/best.pt")
                     async with aiofiles.open(custom_model_local_path, "wb") as f:
                         await f.write(content)
                     return True
                else:
                     logger.info("Custom model 'best.pt' NOT found in storage.")
                     return False
            
            storage_model_exists = False
            try:
                storage_model_exists = asyncio.run(check_and_download_model())
            except Exception as e:
                logger.warning(f"Failed to check storage for model: {e}")

            
            if storage_model_exists and os.path.exists(custom_model_local_path):
                logger.info(f"Loading custom fine-tuned model from {custom_model_local_path}")
                cls._model = YOLO(custom_model_local_path)
                return cls._model
            elif not storage_model_exists and os.path.exists(custom_model_local_path):
                logger.warning("Local custom model found but not present in storage. Ignoring local model and using base model.")
            
            # Fallback to base model
            is_gpu = torch.cuda.is_available()
            logger.info(f"GPU Available: {is_gpu}")

            if is_gpu:
                model_name = "yolo11m-cls.pt"
                url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-cls.pt"
            else:
                model_name = "yolo11n-cls.pt"
                url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-cls.pt"

            model_path = os.path.join(settings.MODELS_DIR, model_name)
            
            if not os.path.exists(model_path):
                 logger.info(f"Model '{model_name}' not found. Downloading...")
                 import requests
                 response = requests.get(url, stream=True)
                 response.raise_for_status()
                 with open(model_path + ".tmp", "wb") as f:
                     shutil.copyfileobj(response.raw, f)
                 shutil.move(model_path + ".tmp", model_path)

            cls._model = YOLO(model_path)

        return cls._model

    @staticmethod
    def get_preferred_image_size():
        """Returns 640 if GPU is available, else 224."""
        try:
            import torch

            if torch.cuda.is_available():
                return 640
        except ImportError:
            pass
        return 224

    @classmethod
    def reload_model(cls):
        """
        Clears the cached model instance to force reloading from disk on next access.
        """
        logger.info("Reloading AI model from disk...")
        cls._model = None
        cls._get_model()

    @classmethod
    def reset_model(cls):
        """
        Deletes all model files from disk and clears the cache to force a fresh download/initialization.
        Useful when hardware changes (e.g. GPU added/removed).
        """
        logger.info("Resetting AI model...")
        cls._model = None

        # Delete all files in models directory
        if os.path.exists(settings.MODELS_DIR):
            for filename in os.listdir(settings.MODELS_DIR):
                file_path = os.path.join(settings.MODELS_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")

        logger.info(
            "Model files deleted. Application will re-download on next request."
        )

    @classmethod
    async def listen_for_updates(cls):
        """
        Listens for Redis messages to reload the model within other workers.
        Intended to be run as a background task in the worker's process.
        """
        redis = RedisClient.get_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe("ai_model_update")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if data == "reload":
                        logger.info("Received reload signal. Reloading model...")
                    if data == "reload":
                        cls.reload_model()
        except Exception as e:
            logger.error(f"Error in AI model update listener: {e}")
        finally:
            await pubsub.unsubscribe("ai_model_update")

    @classmethod
    def predict(cls, tmp_file: str) -> tuple[int, float]:
        # Validate image before passing to model
        try:
            from PIL import Image
            from PIL import UnidentifiedImageError
            # Check file using PIL - sync op
            with Image.open(tmp_file) as img:
                img.verify()  # Verify file integrity
        except (UnidentifiedImageError, OSError) as e:
            logger.error(f"Invalid image file: {tmp_file} - {e}")
            raise ValueError("Podane dane nie są poprawnym zdjęciem")

        model = cls._get_model()
        imgsz = cls.get_preferred_image_size()
        
        # Sync Prediction
        results = model(tmp_file, imgsz=imgsz)

        product_id = -1
        confidence = 0.0

        if results and results[0].probs:
            # Assuming classification model
            top1_idx = results[0].probs.top1
            confidence = float(results[0].probs.top1conf)
            class_name = results[0].names[top1_idx]
            if str(class_name).isdigit():
                product_id = int(class_name)

        return product_id, confidence

    @staticmethod
    async def save_feedback(content: bytes, product_id: int):
        filename = f"{uuid.uuid4()}.jpg"
        # Store in datasets bucket: datasets/product_id/filename.jpg
        path = f"datasets/{product_id}/{filename}"
        await storage.save(path, content)

    @staticmethod
    def _download_dataset(dest_dir: str) -> bool:
        """
        Downloads valid training images from storage to local dest_dir.
        Returns True if data found.
        """
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        
        import asyncio
        import aiofiles

        async def _download_logic():
            # List all files under datasets/
            files = await storage.list("datasets/", recursive=True)
            has_data = False
            
            for file_info in files:
                rel_name = file_info["name"] 
                if not rel_name.strip():
                     continue
                
                ext = os.path.splitext(rel_name)[1].lower()
                if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
                    continue
                
                local_dest = os.path.join(dest_dir, rel_name)
                os.makedirs(os.path.dirname(local_dest), exist_ok=True)
                
                storage_path = f"datasets/{rel_name}"
                try:
                    content = await storage.get(storage_path)
                    async with aiofiles.open(local_dest, "wb") as f:
                        await f.write(content)
                    has_data = True
                except Exception as e:
                    logger.error(f"Failed to download {storage_path}: {e}")
            return has_data

        return asyncio.run(_download_logic())

    @staticmethod
    def _prepare_split_dataset(
        source_dir: str, dest_dir: str, split_ratio: float = 0.8
    ):
        """
        Creates a train/val split structure from dataset directory.
        source_dir: Directory containing "class_name/image.jpg"
        dest_dir: Target directory for train/val structure
        """
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        
        train_dir = os.path.join(dest_dir, "train")
        val_dir = os.path.join(dest_dir, "val")
        os.makedirs(train_dir, exist_ok=True)
        os.makedirs(val_dir, exist_ok=True)

        has_data = False

        # Iterate over each class directory in source
        for class_name in os.listdir(source_dir):
            class_path = os.path.join(source_dir, class_name)
            if not os.path.isdir(class_path):
                continue
            
            # Create class dirs in train/val
            os.makedirs(os.path.join(train_dir, class_name), exist_ok=True)
            os.makedirs(os.path.join(val_dir, class_name), exist_ok=True)

            images = [
                f
                for f in os.listdir(class_path)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp"))
            ]
            
            # Filter out empty files?
            
            random.shuffle(images)
            if images:
                has_data = True

            # Ensure at least 1 image goes to training
            split_idx = int(len(images) * split_ratio)
            if split_idx == 0 and len(images) > 0:
                split_idx = 1
            

            train_imgs = images[:split_idx]
            val_imgs = images[split_idx:]
            
            # Copy files
            for img in train_imgs:
                shutil.copy2(os.path.join(class_path, img), os.path.join(train_dir, class_name, img))
            for img in val_imgs:
                shutil.copy2(os.path.join(class_path, img), os.path.join(val_dir, class_name, img))

        return has_data

    @classmethod
    def retrain_model(cls):
        """
        Retrains the model using the dataset from storage.
        """
        r = RedisClient.get_sync_client()
        lock = r.lock("training_lock", timeout=3600)
        acquired = lock.acquire(blocking=False)
        if not acquired:
            logger.warning("Another worker is currently training. Skipping.")
            return

        logger.info("Starting model retraining...")
        
        session_id = str(uuid.uuid4())
        raw_dataset_dir = os.path.join("/data", "temp", f"raw_data_{session_id}")
        split_dataset_dir = os.path.join("/data", "temp", f"split_data_{session_id}")
        project_dir = os.path.join(settings.MODELS_DIR, "training_runs")
        run_name = f"run_{session_id}"

        import asyncio
        import aiofiles

        try:
            # 1. Download
            logger.info(f"Downloading dataset to {raw_dataset_dir}...")
            has_data = cls._download_dataset(raw_dataset_dir) # Now sync
            if not has_data:
                logger.warning("No training data found. Skipping.")
                return

            # 2. Split
            logger.info(f"Splitting dataset to {split_dataset_dir}...")
            cls._prepare_split_dataset(raw_dataset_dir, split_dataset_dir)
            
            # 3. Train
            model = cls._get_model() # Sync
            
            # Run training (sync)
            logger.info("Starting YOLO training...")
            model.train(
                data=split_dataset_dir,
                epochs=10,
                imgsz=cls.get_preferred_image_size(),
                project=project_dir,
                name=run_name,
                exist_ok=True,
                workers=0, 
            )
            
            # 4. Upload best.pt
            new_model_path = os.path.join(project_dir, run_name, "weights", "best.pt")
            
            async def upload_artifacts():
                if os.path.exists(new_model_path):
                    logger.info("Training completed. Uploading best.pt to storage...")
                    async with aiofiles.open(new_model_path, "rb") as f:
                        content = await f.read()
                        await storage.save("models/best.pt", content)
                    
                    logger.info("Deleting training data from storage...")
                    files = await storage.list("datasets/", recursive=True)
                    for f in files:
                         await storage.delete(f"datasets/{f['name']}")
                    return True
                return False

            success = asyncio.run(upload_artifacts())

            if success:
                r.publish("ai_model_update", "reload")
                logger.info("Reload signal published.")
            else:
                 logger.error("Training completed but 'best.pt' not found.")

        except Exception as e:
            logger.error(f"Error during retraining: {e}")
            raise e
        finally:
             if acquired:
                 lock.release()
             # Cleanup local temp
             if os.path.exists(raw_dataset_dir): shutil.rmtree(raw_dataset_dir)
             if os.path.exists(split_dataset_dir): shutil.rmtree(split_dataset_dir)
             run_dir = os.path.join(project_dir, run_name)
             if os.path.exists(run_dir): shutil.rmtree(run_dir)

    @classmethod
    async def bulk_save_training_data(cls, files: List[UploadFile], product_id: int):
        for file in files:
            filename = f"{uuid.uuid4().hex}.{file.filename.split('.')[-1]}"
            path = f"datasets/{product_id}/{filename}"
            content = await file.read()
            await storage.save(path, content)
