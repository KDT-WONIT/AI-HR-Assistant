from app.config import settings
from app.repositories.memory import MemoryConversationRepository
from app.repositories.mysql import MySQLConversationRepository
from app.repositories.sqlite import SQLiteConversationRepository


def create_repository():
    if settings.storage_backend == "sqlite":
        return SQLiteConversationRepository()
    if settings.storage_backend == "mysql":
        return MySQLConversationRepository()
    return MemoryConversationRepository()
