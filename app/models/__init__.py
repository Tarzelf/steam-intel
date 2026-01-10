"""SQLAlchemy models."""
from app.models.game import Game, GameSnapshot
from app.models.market import (
    GenreSnapshot,
    TopSellersSnapshot,
    NewRelease,
    GenreGame,
    TagCorrelation,
    MarketTrend,
    UpcomingRelease,
)
from app.models.revenue import RevenueRecord
from app.models.analytics import PortfolioBenchmark, GenreScore
from app.models.system import CollectionRun, ApiLog

__all__ = [
    "Game",
    "GameSnapshot",
    "GenreSnapshot",
    "TopSellersSnapshot",
    "NewRelease",
    "GenreGame",
    "TagCorrelation",
    "MarketTrend",
    "UpcomingRelease",
    "RevenueRecord",
    "PortfolioBenchmark",
    "GenreScore",
    "CollectionRun",
    "ApiLog",
]
