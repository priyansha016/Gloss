from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.worker.tasks import process_video


class WorkerSettings:
    functions = [process_video]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    # 60 min: long videos on a slow local model (qwen2.5:14b, concurrency 1) can be lengthy.
    job_timeout = 3600
    cron_jobs: list[cron] = []
