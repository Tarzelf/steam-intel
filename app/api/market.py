"""Market intelligence API endpoints with enhanced data."""
from datetime import date, timedelta
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.auth import verify_api_key
from app.models import GenreSnapshot, TopSellersSnapshot, GenreScore, MarketTrend, TagCorrelation, UpcomingRelease

router = APIRouter(prefix="/market", tags=["market"])


class GenreStatsResponse(BaseModel):
    """Response for genre stats."""
    genre: str
    game_count: Optional[int]
    total_ccu: Optional[int]
    avg_ccu: Optional[int]
    avg_review_score: Optional[int]
    top_games: Optional[list]
    snapshot_date: date


class GenreScoreResponse(BaseModel):
    """Response for genre fitness score."""
    genre: str
    hotness_score: int
    saturation_score: int
    success_rate_score: int
    timing_score: int
    overall_score: int
    recommendation: str
    score_date: date


class TopSellersResponse(BaseModel):
    """Response for top sellers."""
    category: str
    snapshot_date: date
    rankings: list


@router.get("/genres", response_model=list[GenreStatsResponse])
async def get_genres(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get latest stats for all tracked genres."""
    # Get most recent date
    latest_date_result = await db.execute(
        select(GenreSnapshot.snapshot_date)
        .order_by(GenreSnapshot.snapshot_date.desc())
        .limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()

    if not latest_date:
        return []

    # Get all genres for that date
    result = await db.execute(
        select(GenreSnapshot)
        .where(GenreSnapshot.snapshot_date == latest_date)
        .order_by(GenreSnapshot.total_ccu.desc())
    )
    snapshots = result.scalars().all()

    return [
        GenreStatsResponse(
            genre=s.genre,
            game_count=s.game_count,
            total_ccu=s.total_ccu,
            avg_ccu=s.avg_ccu,
            avg_review_score=s.avg_review_score,
            top_games=s.top_games,
            snapshot_date=s.snapshot_date,
        )
        for s in snapshots
    ]


@router.get("/genres/{genre}", response_model=GenreStatsResponse)
async def get_genre(
    genre: str,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get latest stats for a specific genre."""
    result = await db.execute(
        select(GenreSnapshot)
        .where(GenreSnapshot.genre == genre)
        .order_by(GenreSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        return GenreStatsResponse(
            genre=genre,
            game_count=None,
            total_ccu=None,
            avg_ccu=None,
            avg_review_score=None,
            top_games=None,
            snapshot_date=date.today(),
        )

    return GenreStatsResponse(
        genre=snapshot.genre,
        game_count=snapshot.game_count,
        total_ccu=snapshot.total_ccu,
        avg_ccu=snapshot.avg_ccu,
        avg_review_score=snapshot.avg_review_score,
        top_games=snapshot.top_games,
        snapshot_date=snapshot.snapshot_date,
    )


@router.get("/genres/{genre}/score", response_model=GenreScoreResponse)
async def get_genre_score(
    genre: str,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get fitness score for a genre (for submission evaluation)."""
    result = await db.execute(
        select(GenreScore)
        .where(GenreScore.genre == genre)
        .order_by(GenreScore.score_date.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()

    if not score:
        # Return default scores
        return GenreScoreResponse(
            genre=genre,
            hotness_score=50,
            saturation_score=50,
            success_rate_score=50,
            timing_score=50,
            overall_score=50,
            recommendation="unknown",
            score_date=date.today(),
        )

    return GenreScoreResponse(
        genre=score.genre,
        hotness_score=score.hotness_score or 50,
        saturation_score=score.saturation_score or 50,
        success_rate_score=score.success_rate_score or 50,
        timing_score=score.timing_score or 50,
        overall_score=score.overall_score or 50,
        recommendation=score.recommendation or "unknown",
        score_date=score.score_date,
    )


@router.get("/trending")
async def get_trending(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get trending genres (genres with growing CCU)."""
    # Compare last two snapshots for each genre
    today = date.today()
    week_ago = today - timedelta(days=7)

    # Get current scores
    current_result = await db.execute(
        select(GenreSnapshot)
        .where(GenreSnapshot.snapshot_date >= today - timedelta(days=1))
    )
    current_snapshots = {s.genre: s for s in current_result.scalars().all()}

    # Get week-ago scores
    previous_result = await db.execute(
        select(GenreSnapshot)
        .where(GenreSnapshot.snapshot_date <= week_ago)
        .where(GenreSnapshot.snapshot_date >= week_ago - timedelta(days=1))
    )
    previous_snapshots = {s.genre: s for s in previous_result.scalars().all()}

    trending = []
    for genre, current in current_snapshots.items():
        previous = previous_snapshots.get(genre)
        if previous and previous.total_ccu and previous.total_ccu > 0:
            change_pct = ((current.total_ccu - previous.total_ccu) / previous.total_ccu) * 100
            trending.append({
                "genre": genre,
                "current_ccu": current.total_ccu,
                "previous_ccu": previous.total_ccu,
                "change_pct": round(change_pct, 1),
                "direction": "up" if change_pct > 0 else "down",
            })

    return sorted(trending, key=lambda x: x["change_pct"], reverse=True)


@router.get("/top-sellers", response_model=list[TopSellersResponse])
async def get_top_sellers(
    category: str = Query("top_sellers", description="Category: top_sellers, specials, new_releases"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get top sellers for a category."""
    result = await db.execute(
        select(TopSellersSnapshot)
        .where(TopSellersSnapshot.category == category)
        .order_by(TopSellersSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        return []

    return [TopSellersResponse(
        category=snapshot.category,
        snapshot_date=snapshot.snapshot_date,
        rankings=snapshot.rankings or [],
    )]


@router.get("/heatmap")
async def get_genre_heatmap(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get genre heat map data with scores for all tracked genres."""
    # Get latest scores
    latest_date_result = await db.execute(
        select(GenreScore.score_date)
        .order_by(GenreScore.score_date.desc())
        .limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()

    if not latest_date:
        return {"genres": [], "snapshot_date": None}

    # Get all genre scores for that date
    result = await db.execute(
        select(GenreScore)
        .where(GenreScore.score_date == latest_date)
        .order_by(GenreScore.overall_score.desc())
    )
    scores = result.scalars().all()

    # Also get the snapshot data for CCU/game counts
    snapshot_result = await db.execute(
        select(GenreSnapshot)
        .where(GenreSnapshot.snapshot_date == latest_date)
    )
    snapshots = {s.genre: s for s in snapshot_result.scalars().all()}

    genres = []
    for score in scores:
        snapshot = snapshots.get(score.genre)
        genres.append({
            "genre": score.genre,
            "hotness": score.hotness_score,
            "saturation": score.saturation_score,
            "success_rate": score.success_rate_score,
            "timing": score.timing_score,
            "overall": score.overall_score,
            "recommendation": score.recommendation,
            "total_ccu": snapshot.total_ccu if snapshot else 0,
            "game_count": snapshot.game_count if snapshot else 0,
            "avg_review_score": snapshot.avg_review_score if snapshot else 0,
            "top_games": (snapshot.top_games or [])[:5] if snapshot else [],
        })

    return {
        "genres": genres,
        "snapshot_date": latest_date.isoformat(),
    }


@router.get("/heatmap/enhanced")
async def get_enhanced_heatmap(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get enhanced genre heat map with velocity, pricing, and competition data."""
    # Get latest scores
    latest_date_result = await db.execute(
        select(GenreScore.score_date)
        .order_by(GenreScore.score_date.desc())
        .limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()

    if not latest_date:
        return {"genres": [], "snapshot_date": None}

    # Get all genre scores for that date
    result = await db.execute(
        select(GenreScore)
        .where(GenreScore.score_date == latest_date)
        .order_by(GenreScore.overall_score.desc())
    )
    scores = result.scalars().all()

    # Get snapshot data
    snapshot_result = await db.execute(
        select(GenreSnapshot)
        .where(GenreSnapshot.snapshot_date == latest_date)
    )
    snapshots = {s.genre: s for s in snapshot_result.scalars().all()}

    # Get upcoming releases count per genre
    upcoming_result = await db.execute(
        select(UpcomingRelease)
        .where(UpcomingRelease.expected_release >= date.today())
    )
    upcoming_releases = upcoming_result.scalars().all()

    # Count upcoming by genre
    upcoming_by_genre = defaultdict(list)
    for release in upcoming_releases:
        if release.genres:
            for genre in release.genres:
                upcoming_by_genre[genre].append({
                    "name": release.name,
                    "expected_release": release.expected_release.isoformat() if release.expected_release else None,
                    "hype_score": release.hype_score,
                })

    genres = []
    for score in scores:
        snapshot = snapshots.get(score.genre)
        upcoming = upcoming_by_genre.get(score.genre, [])

        genres.append({
            "genre": score.genre,

            # Core scores
            "hotness": score.hotness_score,
            "saturation": score.saturation_score,
            "success_rate": score.success_rate_score,
            "timing": score.timing_score,
            "overall": score.overall_score,
            "recommendation": score.recommendation,

            # Enhanced velocity & trend
            "growth_velocity": score.growth_velocity or 0,
            "trend_direction": score.trend_direction or "stable",
            "competition_score": score.competition_score or 50,
            "revenue_potential": score.revenue_potential_score or 50,
            "discoverability": score.discoverability_score or 50,

            # Pricing insights
            "avg_price_cents": snapshot.avg_price_cents if snapshot else 0,
            "median_price_cents": snapshot.median_price_cents if snapshot else 0,
            "price_distribution": snapshot.price_distribution if snapshot else {},

            # Release activity
            "releases_last_30d": snapshot.releases_last_30d if snapshot else 0,
            "releases_last_90d": snapshot.releases_last_90d if snapshot else 0,
            "early_access_pct": snapshot.early_access_pct if snapshot else 0,

            # Market size
            "total_ccu": snapshot.total_ccu if snapshot else 0,
            "game_count": snapshot.game_count if snapshot else 0,
            "revenue_estimate_millions": round((snapshot.revenue_estimate_cents or 0) / 100000000, 1) if snapshot else 0,

            # Competition intel
            "upcoming_releases_count": len(upcoming),
            "top_upcoming": sorted(upcoming, key=lambda x: x.get("hype_score") or 0, reverse=True)[:3],

            # Tag combos (from top_tags)
            "top_tags": (snapshot.top_tags or [])[:5] if snapshot else [],

            # Top games
            "top_games": (snapshot.top_games or [])[:5] if snapshot else [],
        })

    return {
        "genres": genres,
        "snapshot_date": latest_date.isoformat(),
    }


@router.get("/heatmap/history")
async def get_genre_heatmap_history(
    months: int = Query(3, description="Number of months of history"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get genre heat map history by month."""
    start_date = date.today() - timedelta(days=months * 30)

    # Get all scores in date range
    result = await db.execute(
        select(GenreScore)
        .where(GenreScore.score_date >= start_date)
        .order_by(GenreScore.score_date.asc())
    )
    all_scores = result.scalars().all()

    # Group by month
    monthly_data = defaultdict(lambda: defaultdict(list))
    for score in all_scores:
        month_key = score.score_date.strftime("%Y-%m")
        monthly_data[month_key][score.genre].append({
            "date": score.score_date.isoformat(),
            "hotness": score.hotness_score,
            "saturation": score.saturation_score,
            "overall": score.overall_score,
            "recommendation": score.recommendation,
            "growth_velocity": score.growth_velocity or 0,
            "trend_direction": score.trend_direction or "stable",
        })

    # Aggregate to monthly averages
    history = []
    for month, genres in sorted(monthly_data.items()):
        month_genres = []
        for genre, scores in genres.items():
            avg_hotness = sum(s["hotness"] for s in scores) // len(scores)
            avg_saturation = sum(s["saturation"] for s in scores) // len(scores)
            avg_overall = sum(s["overall"] for s in scores) // len(scores)
            avg_velocity = sum(s["growth_velocity"] for s in scores) // len(scores)
            # Use latest recommendation
            latest_rec = scores[-1]["recommendation"]
            latest_trend = scores[-1]["trend_direction"]

            month_genres.append({
                "genre": genre,
                "hotness": avg_hotness,
                "saturation": avg_saturation,
                "overall": avg_overall,
                "recommendation": latest_rec,
                "growth_velocity": avg_velocity,
                "trend_direction": latest_trend,
            })

        history.append({
            "month": month,
            "genres": sorted(month_genres, key=lambda x: x["overall"], reverse=True),
        })

    return {"history": history}


@router.get("/trends")
async def get_market_trends(
    genre: str = Query(None, description="Filter by genre"),
    weeks: int = Query(12, description="Number of weeks of history"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get weekly trend data for genre(s)."""
    start_date = date.today() - timedelta(weeks=weeks)

    query = select(MarketTrend).where(MarketTrend.week_start >= start_date)
    if genre:
        query = query.where(MarketTrend.genre == genre)
    query = query.order_by(MarketTrend.week_start.asc())

    result = await db.execute(query)
    trends = result.scalars().all()

    if not trends:
        # If no stored trends, compute from snapshots
        return await _compute_trends_from_snapshots(db, genre, weeks)

    # Group by genre
    trends_by_genre = defaultdict(list)
    for trend in trends:
        trends_by_genre[trend.genre].append({
            "week_start": trend.week_start.isoformat(),
            "total_ccu": trend.total_ccu,
            "game_count": trend.game_count,
            "new_releases": trend.new_releases,
            "ccu_change_pct": round(trend.ccu_change_pct or 0, 1),
            "trend_label": trend.trend_label,
        })

    if genre:
        weeks_data = trends_by_genre.get(genre, [])
        overall_trend = _calculate_overall_trend(weeks_data)
        return {
            "genre": genre,
            "weeks": weeks_data,
            "overall_trend": overall_trend,
        }

    return {"genres": dict(trends_by_genre)}


async def _compute_trends_from_snapshots(db: AsyncSession, genre: str, weeks: int):
    """Fallback: compute trends from daily snapshots."""
    start_date = date.today() - timedelta(weeks=weeks)

    query = select(GenreSnapshot).where(GenreSnapshot.snapshot_date >= start_date)
    if genre:
        query = query.where(GenreSnapshot.genre == genre)
    query = query.order_by(GenreSnapshot.snapshot_date.asc())

    result = await db.execute(query)
    snapshots = result.scalars().all()

    # Group by week
    weekly_data = defaultdict(lambda: defaultdict(list))
    for s in snapshots:
        # Get Monday of the week
        week_start = s.snapshot_date - timedelta(days=s.snapshot_date.weekday())
        weekly_data[s.genre][week_start].append(s)

    trends_by_genre = defaultdict(list)
    for g, weeks_dict in weekly_data.items():
        prev_ccu = None
        for week_start in sorted(weeks_dict.keys()):
            week_snapshots = weeks_dict[week_start]
            # Use latest snapshot of the week
            latest = max(week_snapshots, key=lambda x: x.snapshot_date)

            ccu_change = 0
            if prev_ccu and prev_ccu > 0:
                ccu_change = ((latest.total_ccu - prev_ccu) / prev_ccu) * 100

            trend_label = "stable"
            if ccu_change >= 10:
                trend_label = "growing"
            elif ccu_change >= 20:
                trend_label = "surging"
            elif ccu_change <= -10:
                trend_label = "declining"
            elif ccu_change <= -20:
                trend_label = "crashing"

            trends_by_genre[g].append({
                "week_start": week_start.isoformat(),
                "total_ccu": latest.total_ccu,
                "game_count": latest.game_count,
                "new_releases": latest.releases_last_30d or 0,
                "ccu_change_pct": round(ccu_change, 1),
                "trend_label": trend_label,
            })

            prev_ccu = latest.total_ccu

    if genre:
        weeks_data = trends_by_genre.get(genre, [])
        overall_trend = _calculate_overall_trend(weeks_data)
        return {
            "genre": genre,
            "weeks": weeks_data,
            "overall_trend": overall_trend,
        }

    return {"genres": dict(trends_by_genre)}


def _calculate_overall_trend(weeks_data: list) -> str:
    """Calculate overall trend from weekly data."""
    if len(weeks_data) < 2:
        return "stable"

    # Look at recent velocity
    recent = weeks_data[-3:] if len(weeks_data) >= 3 else weeks_data
    avg_change = sum(w.get("ccu_change_pct", 0) for w in recent) / len(recent)

    if avg_change >= 10:
        return "rising"
    elif avg_change <= -10:
        return "declining"
    return "stable"


@router.get("/tag-combos")
async def get_tag_combinations(
    limit: int = Query(20, description="Number of combinations to return"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get profitable tag combinations."""
    # Get latest date
    latest_date_result = await db.execute(
        select(TagCorrelation.snapshot_date)
        .order_by(TagCorrelation.snapshot_date.desc())
        .limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()

    if not latest_date:
        return {"combinations": [], "snapshot_date": None}

    result = await db.execute(
        select(TagCorrelation)
        .where(TagCorrelation.snapshot_date == latest_date)
        .order_by(TagCorrelation.combined_ccu.desc())
        .limit(limit)
    )
    correlations = result.scalars().all()

    return {
        "combinations": [
            {
                "tags": [c.tag_a, c.tag_b],
                "game_count": c.co_occurrence_count,
                "total_ccu": c.combined_ccu,
                "avg_review_score": c.avg_review_score,
                "avg_price_cents": c.avg_price_cents,
                "correlation_strength": round(c.correlation_strength or 0, 2),
                "top_games": c.top_games or [],
            }
            for c in correlations
        ],
        "snapshot_date": latest_date.isoformat(),
    }


@router.get("/upcoming")
async def get_upcoming_releases(
    genre: str = Query(None, description="Filter by genre"),
    limit: int = Query(20, description="Number of releases to return"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get upcoming releases, optionally filtered by genre."""
    query = select(UpcomingRelease).where(
        UpcomingRelease.expected_release >= date.today()
    )

    if genre:
        query = query.where(UpcomingRelease.genres.contains([genre]))

    query = query.order_by(UpcomingRelease.expected_release.asc()).limit(limit)

    result = await db.execute(query)
    releases = result.scalars().all()

    return {
        "releases": [
            {
                "app_id": r.app_id,
                "name": r.name,
                "developer": r.developer,
                "publisher": r.publisher,
                "expected_release": r.expected_release.isoformat() if r.expected_release else None,
                "genres": r.genres or [],
                "tags": r.tags or [],
                "has_demo": r.has_demo,
                "wishlist_estimate": r.wishlist_estimate,
                "hype_score": r.hype_score,
            }
            for r in releases
        ],
        "total_count": len(releases),
    }


@router.get("/scores/all")
async def get_all_genre_scores(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get all genre scores for heat map visualization."""
    # Get latest date
    latest_date_result = await db.execute(
        select(GenreScore.score_date)
        .order_by(GenreScore.score_date.desc())
        .limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()

    if not latest_date:
        return []

    result = await db.execute(
        select(GenreScore)
        .where(GenreScore.score_date == latest_date)
        .order_by(GenreScore.overall_score.desc())
    )

    return [
        {
            "genre": s.genre,
            "hotness_score": s.hotness_score,
            "saturation_score": s.saturation_score,
            "success_rate_score": s.success_rate_score,
            "timing_score": s.timing_score,
            "overall_score": s.overall_score,
            "recommendation": s.recommendation,
            "growth_velocity": s.growth_velocity or 0,
            "trend_direction": s.trend_direction or "stable",
            "competition_score": s.competition_score or 50,
            "revenue_potential_score": s.revenue_potential_score or 50,
            "discoverability_score": s.discoverability_score or 50,
            "score_date": s.score_date.isoformat(),
        }
        for s in result.scalars().all()
    ]
