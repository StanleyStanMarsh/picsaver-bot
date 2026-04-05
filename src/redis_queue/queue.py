from redis import Redis
from rq import Queue

from .config import QUEUE_ADDRESS, QUEUE_PORT

redis_conn = Redis(
    host=QUEUE_ADDRESS,
    port=QUEUE_PORT,
    db=0
)
save_queue = Queue("save", connection=redis_conn)
read_queue = Queue("read", connection=redis_conn)
