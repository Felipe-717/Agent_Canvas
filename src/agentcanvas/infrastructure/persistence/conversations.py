from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentcanvas.domain.chat.entities import ChatMessage, Conversation, MessageRole
from agentcanvas.infrastructure.persistence.models import ChatMessageRow, ConversationRow
from agentcanvas.infrastructure.persistence.repositories import aware


class SqlAlchemyConversationRepository:
    """Implementa `ConversationRepositoryPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            ConversationRow(
                id=conversation.id,
                owner_id=conversation.owner_id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
        await self._session.flush()

    async def get(self, conversation_id: str) -> Conversation | None:
        row = await self._session.get(ConversationRow, conversation_id)
        return _to_conversation(row) if row is not None else None

    async def list_for_owner(self, owner_id: str) -> list[Conversation]:
        statement = (
            select(ConversationRow)
            .where(ConversationRow.owner_id == owner_id)
            .order_by(ConversationRow.updated_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_conversation(row) for row in rows]

    async def update(self, conversation: Conversation) -> None:
        row = await self._session.get(ConversationRow, conversation.id)
        if row is None:
            raise LookupError(f"La conversacion {conversation.id} no existe")
        row.title = conversation.title
        row.updated_at = conversation.updated_at
        await self._session.flush()

    async def delete(self, conversation_id: str) -> None:
        # SQLite no aplica ON DELETE CASCADE salvo que se active por conexion.
        await self._session.execute(
            delete(ChatMessageRow).where(ChatMessageRow.conversation_id == conversation_id)
        )
        await self._session.execute(
            delete(ConversationRow).where(ConversationRow.id == conversation_id)
        )
        await self._session.flush()

    async def add_message(self, message: ChatMessage) -> None:
        self._session.add(
            ChatMessageRow(
                id=message.id,
                conversation_id=message.conversation_id,
                role=str(message.role),
                text=message.text,
                content=message.content,
                created_at=message.created_at,
            )
        )
        await self._session.flush()

    async def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        statement = (
            select(ChatMessageRow)
            .where(ChatMessageRow.conversation_id == conversation_id)
            .order_by(ChatMessageRow.created_at, ChatMessageRow.id)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_message(row) for row in rows]


def _to_conversation(row: ConversationRow) -> Conversation:
    return Conversation(
        id=row.id,
        owner_id=row.owner_id,
        title=row.title,
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
    )


def _to_message(row: ChatMessageRow) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        text=row.text,
        content=row.content,
        created_at=aware(row.created_at),
    )
