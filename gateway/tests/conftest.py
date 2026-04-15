import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import Base, get_db
from app.main import app
import bcrypt

from app.models import Client

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        # Seed test client
        test_client = Client(
            client_id="test-tool",
            client_secret_hash=bcrypt.hashpw(b"test-secret", bcrypt.gensalt()).decode(),
            tool_provider_id="test-tool",
            client_app_id="test-app",
        )
        session.add(test_client)
        await session.commit()
        yield session


@pytest_asyncio.fixture(scope="session")
async def client(db_engine, db_session):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="session")
async def auth_token(client):
    """Return a valid Bearer token for the seeded test-tool client."""
    resp = await client.post(
        "/auth/token",
        data={"client_id": "test-tool", "client_secret": "test-secret", "end_user_id": "test-user"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
