import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.models import Base
from app.core.database import Database


@pytest.fixture(scope="function")
async def test_db():
    """Создаёт временную in-memory базу для тестов (асинхронно)"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    db = Database()
    db.engine = engine
    db.async_session = async_session

    yield db

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_db):
    async with test_db.get_session() as session:
        yield session