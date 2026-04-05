import os
from dotenv import load_dotenv


load_dotenv()

QUEUE_ADDRESS = os.getenv("QUEUE_ADDRESS")
QUEUE_PORT = os.getenv("QUEUE_PORT")
