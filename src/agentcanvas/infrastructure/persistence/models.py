"""Tablas SQLAlchemy.

Deliberadamente separadas de las entidades de dominio: los repositorios traducen
en ambos sentidos. Fusionarlas ahorraria codigo hoy y ataria el dominio al ORM
manana, que es justo lo que la arquitectura hexagonal intenta evitar.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agentcanvas.domain.chat.entities import MessageContent
from agentcanvas.domain.dataset.schema import DatasetSchema
from agentcanvas.domain.visual.dashboard import Placement
from agentcanvas.domain.visual.spec import VisualSpec
from agentcanvas.domain.workbook.structure import TableSpec
from agentcanvas.infrastructure.persistence.types import PydanticJSON


class Base(DeclarativeBase):
    pass


class StoredFileRow(Base):
    __tablename__ = "stored_files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    extension: Mapped[str] = mapped_column(String(16))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_stored_files_owner_checksum", "owner_id", "checksum"),)


class DatasetRow(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    schema_json: Mapped[DatasetSchema] = mapped_column(PydanticJSON(DatasetSchema))
    table_spec: Mapped[TableSpec | None] = mapped_column(
        PydanticJSON(TableSpec), nullable=True
    )
    """Como se recorto la tabla del archivo. Es lo que permite releer el
    archivo del mes siguiente exactamente igual."""

    fingerprint: Mapped[str] = mapped_column(String(32))
    """Denormalizado desde el schema: permite buscar datasets compatibles sin
    deserializar todos los schemas del usuario."""

    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_datasets_owner_fingerprint", "owner_id", "fingerprint"),)


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatMessageRow(Base):
    """Un mensaje de la conversacion.

    `content` guarda adjuntos y artefactos juntos en un JSON: son datos que solo
    tienen sentido dentro de su mensaje y que nunca se consultan por separado.
    De un grafico se guarda su especificacion, jamas sus numeros.
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[MessageContent] = mapped_column(PydanticJSON(MessageContent))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DashboardRow(Base):
    __tablename__ = "dashboards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VisualRow(Base):
    """Un grafico guardado: de donde salen los datos, como se calculan y donde va.

    Ni un solo valor. Esa es la diferencia entre un dashboard que se actualiza
    solo y una captura de pantalla.
    """

    __tablename__ = "visuals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dashboard_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    spec: Mapped[VisualSpec] = mapped_column(PydanticJSON(VisualSpec))
    placement: Mapped[Placement] = mapped_column(PydanticJSON(Placement))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatasetVersionRow(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[str] = mapped_column(String(64), ForeignKey("stored_files.id"))
    storage_key: Mapped[str] = mapped_column(String(512))
    row_count: Mapped[int] = mapped_column(Integer)
    schema_fingerprint: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
