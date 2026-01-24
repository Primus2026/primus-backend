import os
import shutil
from app.core.config import settings
import logging
import uuid
import random
from typing import List
from fastapi import UploadFile, HTTPException
from app.core.redis_client import RedisClient

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
            custom_model_path = os.path.join(settings.MODELS_DIR, "best.pt")
            if os.path.exists(custom_model_path):
                logger.info(f"Loading custom fine-tuned model from {custom_model_path}")
                cls._model = YOLO(custom_model_path)
                return cls._model

            is_gpu = torch.cuda.is_available()
            logger.info(f"GPU Available: {is_gpu}")

            if is_gpu:
                model_name = "yolo11m-cls.pt"
                logger.info(
                    "GPU detected. Using Medium model (yolo11m-cls.pt) for better accuracy."
                )
                # Download URL for YoloV11 Medium
                url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-cls.pt"
            else:
                model_name = "yolo11n-cls.pt"
                logger.info(
                    "No GPU detected. Using Nano model (yolo11n-cls.pt) for speed."
                )
                url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-cls.pt"

            model_path = os.path.join(settings.MODELS_DIR, model_name)

            # Ensure models directory exists
            os.makedirs(settings.MODELS_DIR, exist_ok=True)

            if not os.path.exists(model_path):
                logger.info(f"Model '{model_name}' not found. Downloading...")
                try:
                    # Manual download to avoid CWD permission issues
                    import requests

                    logger.info(f"Downloading from {url}...")
                    response = requests.get(url, stream=True)
                    response.raise_for_status()

                    # Download to temp file first
                    temp_path = model_path + ".tmp"
                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    shutil.move(temp_path, model_path)
                    logger.info("Download complete.")

                except Exception as e:
                    logger.error(f"Failed to download model: {e}")
                    raise Exception(f"Could not find or download model {model_name}")

            # Initialize model
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

            with Image.open(tmp_file) as img:
                img.verify()  # Verify file integrity
        except (UnidentifiedImageError, OSError) as e:
            logger.error(f"Invalid image file: {tmp_file} - {e}")
            raise ValueError("The provided file is not a valid image.")

        model = cls._get_model()
        imgsz = cls.get_preferred_image_size()
        results = model(tmp_file, imgsz=imgsz)

        product_id = -1
        confidence = 0.0

        if results and results[0].probs:
            # Assuming classification model

            # Get top prediction
            top1_idx = results[0].probs.top1
            confidence = float(results[0].probs.top1conf)

            # Check if class name is parsable as an ID
            # results[0].names is a dict {0: 'name', ...}
            class_name = results[0].names[top1_idx]

            # Try to parse class name as product ID or handle mapping
            if str(class_name).isdigit():
                product_id = int(class_name)

        return product_id, confidence

    @staticmethod
    def save_feedback(content: bytes, product_id: int):

        os.makedirs(settings.DATASET_DIR, exist_ok=True)
        os.makedirs(os.path.join(settings.DATASET_DIR, str(product_id)), exist_ok=True)

        filename = f"{uuid.uuid4()}.jpg"
        with open(
            os.path.join(settings.DATASET_DIR, str(product_id), filename), "wb"
        ) as f:
            f.write(content)

    @staticmethod
    def _prepare_training_dataset(
        source_dir: str, dest_dir: str, split_ratio: float = 0.8
    ):
        """
        Creates a train/val split structure from a flat dataset directory.
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
            random.shuffle(images)
            if images:
                has_data = True

            # Ensure at least 1 image goes to training if we have content
            split_idx = int(len(images) * split_ratio)
            if split_idx == 0 and len(images) > 0:
                split_idx = 1

            train_imgs = images[:split_idx]
            val_imgs = images[split_idx:]

            if not val_imgs:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=400,
                    detail=f"Dataset too small for class '{class_name}'. Must have at least 2 images to perform a train/val split. Found {len(images)} images.",
                )

            for img in train_imgs:
                shutil.copy2(
                    os.path.join(class_path, img),
                    os.path.join(train_dir, class_name, img),
                )

            for img in val_imgs:
                shutil.copy2(
                    os.path.join(class_path, img),
                    os.path.join(val_dir, class_name, img),
                )

        return has_data

    @classmethod
    def retrain_model(cls):
        """
        Retrains the model using the dataset directory.
        This method should be called from a celery task.
        """
        r = RedisClient.get_sync_client()
        # Lock expires in 1 hour to prevent permanent deadlocks if worker crashes
        lock = r.lock("training_lock", timeout=3600)

        acquired = lock.acquire(blocking=False)
        if not acquired:
            logger.warning(
                "Another worker is currently training. Skipping this request."
            )
            raise HTTPException(
                status_code=409,
                detail="Another worker is currently training. Skipping this request.",
            )

        logger.info("Starting model retraining...")

        # Temp dir for split dataset
        temp_dataset_dir = os.path.join(
            "/data", "temp", "training_data_" + str(uuid.uuid4())
        )
        project_dir = os.path.join(settings.MODELS_DIR, "training_runs")
        run_name = "latest_run"

        try:
            has_data = cls._prepare_training_dataset(
                settings.DATASET_DIR, temp_dataset_dir
            )

            if not has_data:
                logger.warning("No training data found. Skipping retraining.")
                return

            model = cls._get_model()  # Continue from current best

            # Train using the temp split directory
            results = model.train(
                data=temp_dataset_dir,
                epochs=10,
                imgsz=cls.get_preferred_image_size(),
                project=project_dir,
                name=run_name,
                exist_ok=True,
                workers=0,  # Must be 0 to avoid "daemonic processes are not allowed to have children" in Celery
            )

            new_model_path = os.path.join(project_dir, run_name, "weights", "best.pt")
            target_path = os.path.join(settings.MODELS_DIR, "best.pt")
            backup_path = os.path.join(settings.MODELS_DIR, "best.pt.bak")

            if os.path.exists(new_model_path):
                logger.info(
                    f"Training completed. New model found at {new_model_path}. Updating..."
                )

                # Backup old model
                if os.path.exists(target_path):
                    shutil.move(target_path, backup_path)

                # Move new model to target
                shutil.copy(new_model_path, target_path)

                # Notify all workers to reload
                r = RedisClient.get_sync_client()
                r.publish("ai_model_update", "reload")
                r.close()
                logger.info("Model updated and reload signal published.")

            else:
                logger.error("Training completed but 'best.pt' was not found.")

        except Exception as e:
            logger.error(f"Error during retraining: {e}")
            raise e
        finally:
            if acquired:
                lock.release()
            # Cleanup temporary training data
            if os.path.exists(temp_dataset_dir):
                logger.info(f"Cleaning up temp dataset: {temp_dataset_dir}")
                shutil.rmtree(temp_dataset_dir)

            # Cleanup training run artifacts to free space
            run_dir = os.path.join(project_dir, run_name)
            if os.path.exists(run_dir):
                logger.info(f"Cleaning up training artifacts: {run_dir}")
                shutil.rmtree(run_dir)

    @classmethod
    async def bulk_save_training_data(cls, files: List[UploadFile], product_id: int):

        os.makedirs(settings.DATASET_DIR, exist_ok=True)
        os.makedirs(os.path.join(settings.DATASET_DIR, str(product_id)), exist_ok=True)

        for file in files:
            filename = f"{uuid.uuid4().hex}.{file.filename.split('.')[-1]}"
            with open(
                os.path.join(settings.DATASET_DIR, str(product_id), filename), "wb"
            ) as f:
                content = await file.read()
                f.write(content)
