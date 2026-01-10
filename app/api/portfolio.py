"""Portfolio stats API endpoints."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.auth import verify_api_key
from app.models import Game, GameSnapshot

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class GameStatsResponse(BaseModel):
    """Response model for game stats."""
    app_id: int
    name: str
    developer: Optional[str]
    release_date: Optional[date]
    price: float
    owners_min: Optional[int]
    owners_max: Optional[int]
    ccu: int
    reviews_positive: int
    reviews_negative: int
    review_score: int
    avg_playtime_hours: float
    snapshot_date: date

    class Config:
        from_attributes = True


class PortfolioSummaryResponse(BaseModel):
    """Response model for portfolio summary."""
    total_games: int
    total_ccu: int
    total_reviews: int
    avg_review_score: float
    games: list[GameStatsResponse]


class HistoryPointResponse(BaseModel):
    """Single point in history."""
    date: date
    ccu: int
    reviews_positive: int
    reviews_negative: int
    review_score: int


@router.get("")
async def get_portfolio(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get current stats for all portfolio games.

    Response format matches ALOR Services standard:
    { success: true, data: {...} }
    """
    # Get portfolio games with latest snapshots
    games_result = await db.execute(
        select(Game).where(Game.is_portfolio == True)
    )
    games = games_result.scalars().all()

    game_stats = []
    total_ccu = 0
    total_reviews = 0
    total_score = 0

    for game in games:
        # Get latest snapshot
        snapshot_result = await db.execute(
            select(GameSnapshot)
            .where(GameSnapshot.app_id == game.app_id)
            .order_by(GameSnapshot.snapshot_date.desc())
            .limit(1)
        )
        snapshot = snapshot_result.scalar_one_or_none()

        if snapshot:
            stats = GameStatsResponse(
                app_id=game.app_id,
                name=game.name,
                developer=game.developer,
                release_date=game.release_date,
                price=(game.price_cents or 0) / 100,
                owners_min=snapshot.owners_min,
                owners_max=snapshot.owners_max,
                ccu=snapshot.ccu or 0,
                reviews_positive=snapshot.reviews_positive or 0,
                reviews_negative=snapshot.reviews_negative or 0,
                review_score=snapshot.review_score or 0,
                avg_playtime_hours=(snapshot.avg_playtime_minutes or 0) / 60,
                snapshot_date=snapshot.snapshot_date,
            )
            game_stats.append(stats)
            total_ccu += stats.ccu
            total_reviews += stats.reviews_positive + stats.reviews_negative
            total_score += stats.review_score

    avg_score = total_score / len(game_stats) if game_stats else 0

    return PortfolioSummaryResponse(
        total_games=len(game_stats),
        total_ccu=total_ccu,
        total_reviews=total_reviews,
        avg_review_score=round(avg_score, 1),
        games=sorted(game_stats, key=lambda x: x.ccu, reverse=True),
    )


@router.get("/{app_id}", response_model=GameStatsResponse)
async def get_game(
    app_id: int,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get current stats for a specific game."""
    # Get game
    game_result = await db.execute(
        select(Game).where(Game.app_id == app_id)
    )
    game = game_result.scalar_one_or_none()

    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get latest snapshot
    snapshot_result = await db.execute(
        select(GameSnapshot)
        .where(GameSnapshot.app_id == app_id)
        .order_by(GameSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="No stats available")

    return GameStatsResponse(
        app_id=game.app_id,
        name=game.name,
        developer=game.developer,
        release_date=game.release_date,
        price=(game.price_cents or 0) / 100,
        owners_min=snapshot.owners_min,
        owners_max=snapshot.owners_max,
        ccu=snapshot.ccu or 0,
        reviews_positive=snapshot.reviews_positive or 0,
        reviews_negative=snapshot.reviews_negative or 0,
        review_score=snapshot.review_score or 0,
        avg_playtime_hours=(snapshot.avg_playtime_minutes or 0) / 60,
        snapshot_date=snapshot.snapshot_date,
    )


@router.get("/{app_id}/history", response_model=list[HistoryPointResponse])
async def get_game_history(
    app_id: int,
    period: str = Query("30d", regex="^\\d+d$"),  # e.g., "30d", "90d"
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get historical stats for a game."""
    # Parse period
    days = int(period.rstrip("d"))
    start_date = date.today() - timedelta(days=days)

    # Get snapshots
    result = await db.execute(
        select(GameSnapshot)
        .where(GameSnapshot.app_id == app_id)
        .where(GameSnapshot.snapshot_date >= start_date)
        .order_by(GameSnapshot.snapshot_date.asc())
    )
    snapshots = result.scalars().all()

    return [
        HistoryPointResponse(
            date=s.snapshot_date,
            ccu=s.ccu or 0,
            reviews_positive=s.reviews_positive or 0,
            reviews_negative=s.reviews_negative or 0,
            review_score=s.review_score or 0,
        )
        for s in snapshots
    ]


@router.get("/{app_id}/wow")
async def get_game_wow(
    app_id: int,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get week-over-week changes for a game."""
    today = date.today()
    week_ago = today - timedelta(days=7)

    # Get current snapshot
    current_result = await db.execute(
        select(GameSnapshot)
        .where(GameSnapshot.app_id == app_id)
        .order_by(GameSnapshot.snapshot_date.desc())
        .limit(1)
    )
    current = current_result.scalar_one_or_none()

    # Get week-ago snapshot
    previous_result = await db.execute(
        select(GameSnapshot)
        .where(GameSnapshot.app_id == app_id)
        .where(GameSnapshot.snapshot_date <= week_ago)
        .order_by(GameSnapshot.snapshot_date.desc())
        .limit(1)
    )
    previous = previous_result.scalar_one_or_none()

    if not current:
        raise HTTPException(status_code=404, detail="No stats available")

    def calc_change(current_val, previous_val):
        if previous_val and previous_val > 0:
            return round(((current_val - previous_val) / previous_val) * 100, 1)
        return None

    return {
        "app_id": app_id,
        "current_date": current.snapshot_date,
        "previous_date": previous.snapshot_date if previous else None,
        "ccu": {
            "current": current.ccu,
            "previous": previous.ccu if previous else None,
            "change_pct": calc_change(current.ccu, previous.ccu if previous else None),
        },
        "reviews": {
            "current": (current.reviews_positive or 0) + (current.reviews_negative or 0),
            "new_this_week": (
                ((current.reviews_positive or 0) + (current.reviews_negative or 0)) -
                ((previous.reviews_positive or 0) + (previous.reviews_negative or 0))
                if previous else None
            ),
        },
        "review_score": {
            "current": current.review_score,
            "previous": previous.review_score if previous else None,
            "change": (current.review_score - previous.review_score) if previous else None,
        },
    }
