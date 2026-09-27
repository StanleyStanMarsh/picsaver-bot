from aiogram.types import User as TgUser

from db.repositories import UsersRepository
from db.session import get_sessionmaker


class UsersService:
    def __init__(self, repo: UsersRepository | None = None) -> None:
        self._repo = repo or UsersRepository()

    async def register_or_update_from_telegram(self, tg_user: TgUser) -> None:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await self._repo.upsert_from_telegram(
                session,
                telegram_id=tg_user.id,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                username=tg_user.username,
                language_code=tg_user.language_code,
                is_premium=bool(tg_user.is_premium) if tg_user.is_premium is not None else False,
            )
            await session.commit()

