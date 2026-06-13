import asyncio
import signal

from app.data.database import initialize_database
from app.services.learning_worker import LearningJobWorkerService


async def main() -> None:
    initialize_database(seed=True)
    worker = LearningJobWorkerService()
    if not worker.enabled:
        return
    await worker.start()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)
    try:
        await stop_event.wait()
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
