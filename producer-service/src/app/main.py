import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings
from app.models import TrackEventResponse, UserActivityEvent
from app.rabbitmq_client import RabbitMQPublisher


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.publisher = RabbitMQPublisher(settings)
    logger.info("Producer service started")
    try:
        yield
    finally:
        app.state.publisher.close()
        logger.info("Producer service shutdown complete")


app = FastAPI(title="User Activity Producer Service", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Invalid request payload",
            "errors": exc.errors(),
        },
    )


def get_publisher(request: Request) -> RabbitMQPublisher:
    return request.app.state.publisher


@app.get("/health")
def health(publisher: RabbitMQPublisher = Depends(get_publisher)) -> dict[str, str]:
    if not publisher.check_health():
        raise HTTPException(status_code=503, detail="RabbitMQ connection is not healthy")

    return {"status": "ok", "service": settings.app_name}


@app.post(
    "/api/v1/events/track",
    response_model=TrackEventResponse,
    status_code=202,
)
def track_event(
    event: UserActivityEvent,
    publisher: RabbitMQPublisher = Depends(get_publisher),
) -> TrackEventResponse:
    payload = event.model_dump(mode="json")

    try:
        publisher.publish_event(payload)
    except Exception as error:
        logger.error("Failed to publish event: %s", error)
        raise HTTPException(status_code=503, detail="Unable to enqueue event") from error

    return TrackEventResponse(message="Event accepted and queued")
