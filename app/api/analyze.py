"""Game analysis API endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.auth import verify_api_key
from app.models import Game, GameSnapshot, GenreScore
from app.collectors import SteamSpyCollector, SteamStoreCollector

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeGameRequest(BaseModel):
    """Request to analyze a Steam game."""
    app_id: int


class ComparableRequest(BaseModel):
    """Request to find comparable games."""
    tags: list[str]
    price_min: Optional[float] = None
    price_max: Optional[float] = None


class GameAnalysisResponse(BaseModel):
    """Full analysis of a game."""
    app_id: int
    name: str
    developer: Optional[str]
    publisher: Optional[str]
    price: float
    genres: list[str]
    tags: list[str]

    # Performance
    owners_estimate: str
    ccu: int
    avg_playtime_hours: float
    review_score: int
    total_reviews: int

    # Market context
    genre_scores: list[dict]
    comparable_games: list[dict]

    # Assessment
    market_fit_score: int
    assessment: str


@router.post("/game", response_model=GameAnalysisResponse)
async def analyze_game(
    request: AnalyzeGameRequest,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Analyze a game from Steam (fetch fresh data if needed)."""
    app_id = request.app_id

    # Check if we have recent data
    game_result = await db.execute(
        select(Game).where(Game.app_id == app_id)
    )
    game = game_result.scalar_one_or_none()

    snapshot_result = await db.execute(
        select(GameSnapshot)
        .where(GameSnapshot.app_id == app_id)
        .order_by(GameSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()

    # If no data, fetch from SteamSpy
    if not game or not snapshot:
        async with SteamSpyCollector(db) as collector:
            await collector._collect_game(app_id)
            await db.commit()

        # Re-fetch
        game_result = await db.execute(
            select(Game).where(Game.app_id == app_id)
        )
        game = game_result.scalar_one_or_none()

        snapshot_result = await db.execute(
            select(GameSnapshot)
            .where(GameSnapshot.app_id == app_id)
            .order_by(GameSnapshot.snapshot_date.desc())
            .limit(1)
        )
        snapshot = snapshot_result.scalar_one_or_none()

    if not game or not snapshot:
        raise HTTPException(status_code=404, detail="Could not fetch game data")

    # Get genre scores
    genre_scores = []
    for tag in (game.tags or [])[:5]:
        score_result = await db.execute(
            select(GenreScore)
            .where(GenreScore.genre == tag)
            .order_by(GenreScore.score_date.desc())
            .limit(1)
        )
        score = score_result.scalar_one_or_none()
        if score:
            genre_scores.append({
                "genre": tag,
                "hotness": score.hotness_score,
                "saturation": score.saturation_score,
                "overall": score.overall_score,
                "recommendation": score.recommendation,
            })

    # Find comparable games
    comparable = await _find_comparable_games(db, game.tags or [], game.price_cents or 0)

    # Calculate market fit score
    avg_genre_score = sum(g.get("overall", 50) for g in genre_scores) / len(genre_scores) if genre_scores else 50
    review_factor = min(100, (snapshot.review_score or 0))
    market_fit = int((avg_genre_score + review_factor) / 2)

    # Generate assessment
    assessment = _generate_assessment(
        market_fit,
        snapshot.review_score or 0,
        snapshot.ccu or 0,
        genre_scores
    )

    return GameAnalysisResponse(
        app_id=app_id,
        name=game.name,
        developer=game.developer,
        publisher=game.publisher,
        price=(game.price_cents or 0) / 100,
        genres=game.genres or [],
        tags=game.tags or [],
        owners_estimate=f"{snapshot.owners_min:,} - {snapshot.owners_max:,}",
        ccu=snapshot.ccu or 0,
        avg_playtime_hours=(snapshot.avg_playtime_minutes or 0) / 60,
        review_score=snapshot.review_score or 0,
        total_reviews=(snapshot.reviews_positive or 0) + (snapshot.reviews_negative or 0),
        genre_scores=genre_scores,
        comparable_games=comparable,
        market_fit_score=market_fit,
        assessment=assessment,
    )


@router.post("/comparable")
async def find_comparable(
    request: ComparableRequest,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Find comparable games based on tags and price."""
    price_cents = None
    if request.price_min is not None or request.price_max is not None:
        price_cents = int(((request.price_min or 0) + (request.price_max or 30)) / 2 * 100)

    return await _find_comparable_games(db, request.tags, price_cents)


async def _find_comparable_games(
    db: AsyncSession,
    tags: list[str],
    price_cents: Optional[int]
) -> list[dict]:
    """Find games with similar tags and price."""
    if not tags:
        return []

    # Simple approach: find games with overlapping tags
    # In production, this would be more sophisticated
    query = select(Game, GameSnapshot).join(
        GameSnapshot,
        Game.app_id == GameSnapshot.app_id
    ).where(
        Game.tags.overlap(tags)
    ).order_by(
        GameSnapshot.ccu.desc()
    ).limit(10)

    result = await db.execute(query)
    rows = result.all()

    comparable = []
    for game, snapshot in rows:
        tag_overlap = len(set(game.tags or []) & set(tags))
        comparable.append({
            "app_id": game.app_id,
            "name": game.name,
            "tags": game.tags[:5] if game.tags else [],
            "tag_overlap": tag_overlap,
            "ccu": snapshot.ccu,
            "owners": f"{snapshot.owners_min:,} - {snapshot.owners_max:,}",
            "review_score": snapshot.review_score,
            "price": (game.price_cents or 0) / 100,
        })

    return sorted(comparable, key=lambda x: x["tag_overlap"], reverse=True)


def _generate_assessment(
    market_fit: int,
    review_score: int,
    ccu: int,
    genre_scores: list[dict]
) -> str:
    """Generate a text assessment of the game."""
    parts = []

    # Market fit
    if market_fit >= 70:
        parts.append("Strong market fit based on genre trends.")
    elif market_fit >= 50:
        parts.append("Moderate market fit.")
    else:
        parts.append("Challenging market positioning.")

    # Reviews
    if review_score >= 80:
        parts.append("Excellent player reception.")
    elif review_score >= 70:
        parts.append("Positive player reviews.")
    elif review_score >= 50:
        parts.append("Mixed reviews - room for improvement.")
    else:
        parts.append("Review score indicates significant player concerns.")

    # Active players
    if ccu >= 1000:
        parts.append("Strong active player base.")
    elif ccu >= 100:
        parts.append("Healthy concurrent player count.")
    elif ccu >= 10:
        parts.append("Modest active player base.")
    else:
        parts.append("Low current player activity.")

    # Genre recommendations
    hot_genres = [g["genre"] for g in genre_scores if g.get("recommendation") == "hot"]
    if hot_genres:
        parts.append(f"Tags in hot genres: {', '.join(hot_genres[:3])}.")

    return " ".join(parts)
