from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from config.settings import settings
from app.core.models import Base

import logging
logger = logging.getLogger(__name__)


class Database:
    """Управление подключением к базе данных"""

    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def create_tables(self):
        """Создает все таблицы в БД"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Таблицы созданы успешно")

    def drop_tables(self):
        """Удаляет все таблицы (только для тестов!)"""
        Base.metadata.drop_all(bind=self.engine)
        logger.info("Таблицы удалены")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Контекстный менеджер для сессий"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка в сессии: {e}")
            raise
        finally:
            session.close()


# Создаем глобальный экземпляр
db = Database()