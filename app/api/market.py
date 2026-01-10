"""Market intelligence API endpoints."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
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
