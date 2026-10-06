import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.database import init_db, SessionLocal
from app.mock.seed_data import seed_database
from app.api import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown hooks."""
    logger.info("Initializing JARVIS Autonomous AI Operating System Backend...")
    try:
        init_db()
        # Seed initial telemetry data if database is empty
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
        logger.info("JARVIS Core subsystems successfully synchronized.")
    except Exception as e:
        logger.error(f"Startup initialization encountered an error: {e}")

    yield

    logger.info("Shutting down JARVIS Core...")


app = FastAPI(
    title="JARVIS Autonomous AI Agent API",
    description=(
        "Autonomous Multimodal AI Agent Backend for Intelligent Computer Interaction, "
        "Task Automation, Reasoning Pipeline, and Dynamic CMS."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# 5. Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing and logging middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response


# 19. Centralized Error Handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "details": exc.errors(),
            "path": request.url.path
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred within JARVIS Core.",
            "path": request.url.path
        },
    )


# 7. Health Check
@app.get("/health", tags=["Health"], summary="System Health Check")
def health_check():
    """
    JARVIS Primary Health Endpoint.
    Returns status: online and service identifier.
    """
    return {
        "status": "online",
        "service": "JARVIS backend",
        "timestamp": time.time(),
        "version": "1.0.0"
    }


# 6. Include API V1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
