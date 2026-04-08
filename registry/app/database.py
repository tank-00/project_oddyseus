import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./registry_test.db")

# For PostgreSQL, scope every connection to the 'registry' schema so that
# registry tables (assets, asset_acl, used_tokens, alembic_version) are
# isolated from the gateway's public-schema tables (clients, transactions).
# SQLite (used in tests) has no schema concept and ignores connect_args.
_connect_args: dict = {}
if DATABASE_URL.startswith("postgresql"):
    _connect_args = {"options": "-c search_path=registry"}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
