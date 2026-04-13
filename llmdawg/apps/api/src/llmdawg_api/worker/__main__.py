"""python -m llmdawg_api.worker entry point."""
import asyncio
from llmdawg_api.worker.worker import run_worker

asyncio.run(run_worker())
