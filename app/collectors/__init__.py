"""Data collectors for Steam APIs."""
from app.collectors.steamspy import SteamSpyCollector
from app.collectors.store import SteamStoreCollector
from app.collectors.partner import SteamPartnerCollector
from app.collectors.genres import GenreCollector
from app.collectors.correlations import TagCorrelationCollector
from app.collectors.upcoming import UpcomingReleasesCollector

__all__ = [
    "SteamSpyCollector",
    "SteamStoreCollector",
    "SteamPartnerCollector",
    "GenreCollector",
    "TagCorrelationCollector",
    "UpcomingReleasesCollector",
]
