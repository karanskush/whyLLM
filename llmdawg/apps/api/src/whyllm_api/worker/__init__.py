"""whyllm background worker — consumes the Redis ingest queue.

Entry point:
    python -m whyllm_api.worker

The worker does NOT use arq's job format (arq uses sorted sets + its own
serialization). Instead it uses raw BRPOP on the ingest_queue list — the same
format the ingest API pushes to with LPUSH.

Exports:
    IngestWorker  — lifecycle class (start/stop)
    run_worker    — coroutine that blocks until SIGTERM
"""

from whyllm_api.worker.worker import IngestWorker, run_worker

__all__ = ["IngestWorker", "run_worker"]
