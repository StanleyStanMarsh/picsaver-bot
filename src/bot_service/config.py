import os
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

PROXY_PROTO = os.getenv("PROXY_PROTO")
PROXY_ADDRESS = os.getenv("PROXY_ADDRESS")
PROXY_PORT = os.getenv("PROXY_PORT")

PROXY_FULL_ADDRESS = f"{PROXY_PROTO}://{PROXY_ADDRESS}:{PROXY_PORT}"
PROXY_KEY = os.getenv("PROXY_KEY")
