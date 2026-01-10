"""Background task scheduler for data collection."""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.database import async_session_maker
from app.collectors import (
    SteamSpyCollector,
    SteamStoreCollector,
    SteamPartnerCollector,
    GenreCollector,
    TagCorrelationCollector,
    UpcomingReleasesCollector,
)

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()


async def collect_portfolio_stats():
    """Scheduled job: Collect stats for portfolio games."""
    logger.info("Starting scheduled portfolio collection")
    async with async_session_maker() as session:
        async with SteamSpyCollector(session) as collector:
            await collector.collect()


async def collect_market_data():
    """Scheduled job: Collect market intelligence."""
    logger.info("Starting scheduled market collection")
    async with async_session_maker() as session:
        async with SteamStoreCollector(session) as collector:
            await collector.collect()


async def collect_genre_trends():
    """Scheduled job: Collect genre/tag trend data."""
    logger.info("Starting scheduled genre collection")
    async with async_session_maker() as session:
        async with GenreCollector(session) as collector:
            await collector.collect()


async def collect_revenue():
    """Scheduled job: Collect revenue data (if Partner API available)."""
    if not settings.steam_partner_key:
        logger.info("Skipping revenue collection - no Partner API key")
        return

    logger.info("Starting scheduled revenue collection")
    async with async_session_maker() as session:
        async with SteamPartnerCollector(session) as collector:
            await collector.collect()


async def collect_tag_correlations():
    """Scheduled job: Analyze tag correlations for market insights."""
    logger.info("Starting scheduled tag correlation analysis")
    async with async_session_maker() as session:
        async with TagCorrelationCollector(session) as collector:
            await collector.collect()


async def collect_upcoming_releases():
    """Scheduled job: Collect upcoming releases for competitive intel."""
    logger.info("Starting scheduled upcoming releases collection")
    async with async_session_maker() as session:
        async with UpcomingReleasesCollector(session) as collector:
            await collector.collect()


def start_scheduler():
    """Start the background scheduler with all jobs."""
    # Portfolio stats - every 6 hours by default
    scheduler.add_job(
        collect_portfolio_stats,
        trigger=IntervalTrigger(hours=settings.collection_interval_hours),
        id="portfolio_stats",
        name="Collect Portfolio Stats",
        replace_existing=True,
        next_run_time=datetime.utcnow(),  # Run immediately on startup
    )

    # Market data - daily by default
    scheduler.add_job(
        collect_market_data,
        trigger=IntervalTrigger(hours=settings.market_collection_interval_hours),
        id="market_data",
        name="Collect Market Data",
        replace_existing=True,
    )

    # Genre trends - daily (runs after market data)
    scheduler.add_job(
        collect_genre_trends,
        trigger=IntervalTrigger(hours=24),
        id="genre_trends",
        name="Collect Genre Trends",
        replace_existing=True,
    )

    # Revenue - daily by default (only if Partner API configured)
    if settings.steam_partner_key:
        scheduler.add_job(
            collect_revenue,
            trigger=IntervalTrigger(hours=settings.revenue_collection_interval_hours),
            id="revenue",
            name="Collect Revenue Data",
            replace_existing=True,
        )

    # Tag correlations - daily (runs after genre collection)
    scheduler.add_job(
        collect_tag_correlations,
        trigger=IntervalTrigger(hours=24),
        id="tag_correlations",
        name="Analyze Tag Correlations",
        replace_existing=True,
    )

    # Upcoming releases - every 12 hours
    scheduler.add_job(
        collect_upcoming_releases,
        trigger=IntervalTrigger(hours=12),
        id="upcoming_releases",
        name="Collect Upcoming Releases",
        replace_existing=True,
    )

    scheduler.start()
    jobs = ["portfolio_stats", "market_data", "genre_trends", "tag_correlations", "upcoming_releases"]
    if settings.steam_partner_key:
        jobs.append("revenue")
    logger.info(f"Scheduler started with jobs: {', '.join(jobs)}")


def stop_scheduler():
    """Stop the scheduler."""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
