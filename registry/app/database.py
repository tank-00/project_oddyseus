import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./registry_test.db")

# For PostgreSQL, scope every connection to the 'registry' schema so that
# registry tables (assets, asset_acl, used_tokens, alembic_version) are
# isolated from the gateway's public-schema tables (clients, transactions).
# SQLite (used in tests) has no schema concept and ignores connect_args.
_connect_args: dict = {}
if DATABASE_URL.startswith("postgresql"):
    _connect_args = {"server_settings": {"search_path": "registry"}}

engine = create_async_engine(DATABASE_URL, connect_args=_connect_args, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
