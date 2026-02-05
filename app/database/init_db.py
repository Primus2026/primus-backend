import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService

logger = logging.getLogger("INIT_DB")

async def init_db(db: AsyncSession) -> None:
    try:
        logger.info("Checking/Creating admin user...")
        # UserService.create_admin handles the check internally
        await UserService.create_admin(db)
        logger.info("Admin user check completed.")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
