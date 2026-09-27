from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User


class UsersRepository:
    async def upsert_from_telegram(
        self,
        session: AsyncSession,
        *,
        telegram_id: int,
        first_name: str | None,
        last_name: str | None,
        username: str | None,
        language_code: str | None,
        is_premium: bool,
    ) -> User:
        now = datetime.now(tz=timezone.utc)

        existing = await session.scalar(
            select(User).where(User.telegram_id == telegram_id).limit(1)
        )

        if existing is None:
            user = User(
                telegram_id=telegram_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
                language_code=language_code,
                is_premium=is_premium,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            return user

        existing.first_name = first_name
        existing.last_name = last_name
        existing.username = username
        existing.language_code = language_code
        existing.is_premium = is_premium
        existing.updated_at = now
        return existing

