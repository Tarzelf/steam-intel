"""Steam Intelligence Service - FastAPI Application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.api import portfolio_router, market_router, analyze_router, revenue_router, steam_news_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Steam Intelligence Service")
    await init_db()
    start_scheduler()

    yield

    # Shutdown
    logger.info("Shutting down Steam Intelligence Service")
    stop_scheduler()


# Create application
app = FastAPI(
    title="Steam Intelligence Service",
    description="Game analytics and market intelligence API for First Break Labs",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check (no auth required) - ALOR Services standard
@app.get("/health")
async def health_check():
    """Health check endpoint (ALOR Services standard)."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "service": "steam-intel"}


from datetime import datetime


# Root info
@app.get("/")
async def root():
    """API information."""
    return {
        "service": "Steam Intelligence Service",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Include routers
app.include_router(portfolio_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(revenue_router, prefix="/api/v1")
app.include_router(steam_news_router, prefix="/api/v1")


# Manual trigger endpoints (for admin use)
@app.post("/api/v1/admin/collect/portfolio")
async def trigger_portfolio_collection(request: Request):
    """Manually trigger portfolio stats collection."""
    from app.api.auth import verify_api_key
    await verify_api_key(request.headers.get("X-API-Key"))

    from app.scheduler import collect_portfolio_stats
    await collect_portfolio_stats()
    return {"status": "completed", "job": "portfolio_stats"}


@app.post("/api/v1/admin/collect/market")
async def trigger_market_collection(request: Request):
    """Manually trigger market data collection."""
    from app.api.auth import verify_api_key
    await verify_api_key(request.headers.get("X-API-Key"))

    from app.scheduler import collect_market_data
    await collect_market_data()
    return {"status": "completed", "job": "market_data"}


@app.post("/api/v1/admin/collect/genres")
async def trigger_genre_collection(request: Request):
    """Manually trigger genre trends collection."""
    from app.api.auth import verify_api_key
    await verify_api_key(request.headers.get("X-API-Key"))

    from app.scheduler import collect_genre_trends
    await collect_genre_trends()
    return {"status": "completed", "job": "genre_trends"}


# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
