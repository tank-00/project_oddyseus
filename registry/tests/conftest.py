import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.store import LocalFileStore, get_store

TEST_DB_URL = "sqlite://"


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def tmp_storage(tmp_path_factory):
    return tmp_path_factory.mktemp("asset_storage")


@pytest_asyncio.fixture(scope="session")
async def client(db_engine, tmp_storage):
    session_factory = sessionmaker(db_engine, expire_on_commit=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def override_get_store():
        return LocalFileStore(str(tmp_storage))

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_store] = override_get_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
