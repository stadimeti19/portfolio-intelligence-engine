from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_intelligence.storage.models import Base, SchemaVersion

SCHEMA_VERSION = "0.1.0"


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        existing = session.scalar(select(SchemaVersion).limit(1))
        if existing is None:
            session.add(SchemaVersion(id=1, version=SCHEMA_VERSION))
            session.commit()
