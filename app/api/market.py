"""Market intelligence API endpoints."""
from datetime import date, timedelta
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.auth import verify_api_key
from app.models import GenreSnapshot, TopSellersSnapshot, GenreScore

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
        })

    # Aggregate to monthly averages
    history = []
    for month, genres in sorted(monthly_data.items()):
        month_genres = []
        for genre, scores in genres.items():
            avg_hotness = sum(s["hotness"] for s in scores) // len(scores)
            avg_saturation = sum(s["saturation"] for s in scores) // len(scores)
            avg_overall = sum(s["overall"] for s in scores) // len(scores)
            # Use latest recommendation
            latest_rec = scores[-1]["recommendation"]

            month_genres.append({
                "genre": genre,
                "hotness": avg_hotness,
                "saturation": avg_saturation,
                "overall": avg_overall,
                "recommendation": latest_rec,
            })

        history.append({
            "month": month,
            "genres": sorted(month_genres, key=lambda x: x["overall"], reverse=True),
        })

    return {"history": history}


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
            "score_date": s.score_date.isoformat(),
        }
        for s in result.scalars().all()
    ]
