#!/usr/bin/env python3
import os, sys, time
from urllib.parse import urlparse
from minio import Minio

endpoint = os.environ["MINIO_ENDPOINT"]
u = urlparse(endpoint)
host = u.netloc or u.path
client = Minio(
    host,
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=u.scheme == "https",
)
bucket = os.environ["MINIO_BUCKET"]
last = None
for i in range(40):
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        print(f"bucket ready: {bucket}", flush=True)
        sys.exit(0)
    except Exception as e:
        last = e
        print(f"wait minio {i}: {e}", flush=True)
        time.sleep(1)
print(f"minio bucket init failed: {last}", flush=True)
sys.exit(1)
