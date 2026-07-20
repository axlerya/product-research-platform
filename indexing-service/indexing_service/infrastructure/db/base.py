"""Базовый слой SQLAlchemy 2.0: ``Base``, naming convention, типы.

Единая ``MetaData`` с naming_convention обязательна: без неё Alembic
даёт нестабильные имена constraint'ов.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from sqlalchemy import CHAR, DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Общий декларативный базовый класс ORM-моделей."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Переиспользуемые аннотированные типы (единый маппинг Python -> PG).
uuid_pk = Annotated[UUID, mapped_column(PgUUID(as_uuid=True), primary_key=True)]
sha256_hex = Annotated[str, mapped_column(CHAR(64))]
ts_tz = Annotated[datetime, mapped_column(DateTime(timezone=True))]
