from utils import setup_logger

setup_logger()

import asyncio
from bot_service import main


if __name__ == "__main__":
    asyncio.run(main())