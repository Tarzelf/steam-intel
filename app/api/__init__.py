"""API routes."""
from app.api.portfolio import router as portfolio_router
from app.api.market import router as market_router
from app.api.analyze import router as analyze_router
from app.api.revenue import router as revenue_router

__all__ = [
    "portfolio_router",
    "market_router",
    "analyze_router",
    "revenue_router",
]
