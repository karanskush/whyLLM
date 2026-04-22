"""python -m whyllm_api.worker entry point."""
import asyncio
from whyllm_api.worker.worker import run_worker

asyncio.run(run_worker())
