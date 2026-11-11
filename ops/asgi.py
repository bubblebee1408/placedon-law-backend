"""ASGI entrypoint: the gateway WITH its Postgres job queue.

`create_app()` with no queue serves uploads as PENDING forever ("No queue is configured"), so
both the hosted service and the local stack (compose.yaml) start from here:

    python -m uvicorn ops.asgi:app

Keys come from the PLACEDON_GATEWAY_* service environment (see .env.example).
ponytail: drop this file once create_app defaults the Postgres queue when a database is set.
"""
import os

from gateway.app import create_app
from gateway.jobs import PostgresQueue
from gateway.models import check_answer_model_at_startup
from gateway.store import database_url

check_answer_model_at_startup()      # PLACEDON_ANSWER_MODEL=gemini without Vertex asia-south1
_url = database_url()
app = create_app(db_url=_url, queue=PostgresQueue(
    _url, tenant_id=os.environ["PLACEDON_GATEWAY_TENANT_ID"],
    actor_id=os.environ["PLACEDON_GATEWAY_ACTOR_ID"]))
