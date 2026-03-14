import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.config import Settings
from app.db import MySQLActivityRepository
from app.worker import ConsumerWorker, EventProcessor


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = Settings()
repository = MySQLActivityRepository(settings)
processor = EventProcessor(repository, settings)
worker = ConsumerWorker(settings, repository, processor)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.worker = worker
    worker.start()
    logger.info("Consumer service started")
    try:
        yield
    finally:
        worker.stop()
        logger.info("Consumer service shutdown complete")


app = FastAPI(title="User Activity Consumer Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    status = worker.health_status()
    if not status["healthy"]:
        raise HTTPException(status_code=503, detail=status)
    return status
