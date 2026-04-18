from collections.abc import Iterator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

connect_args = {"check_same_thread": False}
engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args=connect_args,
    poolclass=StaticPool if settings.db_url.endswith(":memory:") else None,
)


def init_db() -> None:
    from app import models  # noqa: F401  ensure tables registered

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
