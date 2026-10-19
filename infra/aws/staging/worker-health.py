"""Check the existing worker process, database and queue without invoking AI."""

from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.workers.ai_analysis import create_sqs_client

if b"app.workers.ai_analysis" not in Path("/proc/1/cmdline").read_bytes():
    raise SystemExit(1)
with engine.connect() as connection:
    connection.execute(text("SELECT 1"))
create_sqs_client().get_queue_attributes(
    QueueUrl=settings.AI_ANALYSIS_QUEUE_URL, AttributeNames=["QueueArn"]
)
