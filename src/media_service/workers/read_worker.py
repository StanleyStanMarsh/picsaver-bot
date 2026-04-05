from redis import Redis
from rq import Worker

from redis_queue import QUEUE_ADDRESS, QUEUE_PORT

import logging

logging.basicConfig(level=logging.INFO)

queues = ["read"]

redis_conn = Redis(
    host=QUEUE_ADDRESS,
    port=QUEUE_PORT,
    db=0
)


if __name__ == "__main__":
    worker = Worker(queues, connection=redis_conn, name="Image Reader")
    worker.work()
