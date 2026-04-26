"""MongoDB client and index management."""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.config import get_settings

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient | None = None
database: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """Connect to MongoDB and initialize indexes."""
    global client, database

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    database = client[settings.mongo_db_name]
    await ensure_indexes(database)
    logger.info("MongoDB connection established")


async def close_mongo_connection() -> None:
    """Close MongoDB connection."""
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    """Return active database connection."""
    if database is None:
        raise RuntimeError("Database connection is not initialized")
    return database


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create required indexes for production performance."""
    await db.users.create_index([("email", ASCENDING)], unique=True, background=True)
    await db.users.create_index([("created_at", DESCENDING)], background=True)

    await db.otp_sessions.create_index([("email", ASCENDING), ("created_at", DESCENDING)], background=True)
    await db.otp_sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, background=True)

    await db.prescriptions.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], background=True)
    await db.prescriptions.create_index([("user_id", ASCENDING), ("status", ASCENDING)], background=True)
    await db.prescriptions.create_index([("content_hash", ASCENDING)], background=True)

    await db.medicines.create_index([("user_id", ASCENDING), ("name_normalized", ASCENDING)], background=True)
    await db.medicines.create_index([("prescription_id", ASCENDING)], background=True)

    await db.dose_logs.create_index([("user_id", ASCENDING), ("scheduled_for", ASCENDING)], background=True)
    await db.dose_logs.create_index([("status", ASCENDING), ("scheduled_for", ASCENDING)], background=True)

    await db.alerts.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], background=True)
    await db.alerts.create_index([("delivery_status", ASCENDING), ("created_at", DESCENDING)], background=True)
    await db.events.create_index([("created_at", DESCENDING)], background=True)

    await db.caregivers.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], background=True)
    await db.caregivers.create_index(
        [("user_id", ASCENDING), ("email", ASCENDING)],
        unique=True,
        background=True,
        partialFilterExpression={"deleted_at": None},
    )
