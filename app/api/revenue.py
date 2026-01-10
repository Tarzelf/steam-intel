"""Revenue API endpoints."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.auth import verify_api_key
from app.models import RevenueRecord, Game

router = APIRouter(prefix="/revenue", tags=["revenue"])


class RevenueSummaryResponse(BaseModel):
    """Revenue summary for portfolio."""
    total_gross_cents: int
    total_net_cents: int
    total_units: int
    period_start: date
    period_end: date
    by_game: list[dict]


class GameRevenueResponse(BaseModel):
    """Revenue for a single game."""
    app_id: int
    name: str
    total_gross_cents: int
    total_net_cents: int
    total_units: int
    periods: list[dict]


@router.get("/summary", response_model=RevenueSummaryResponse)
async def get_revenue_summary(
    period: str = Query("30d", regex="^\\d+d$"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get revenue summary for all portfolio games."""
    days = int(period.rstrip("d"))
    start_date = date.today() - timedelta(days=days)

    # Aggregate by game
    result = await db.execute(
        select(
            RevenueRecord.app_id,
            func.sum(RevenueRecord.gross_revenue_cents).label("gross"),
            func.sum(RevenueRecord.net_revenue_cents).label("net"),
            func.sum(RevenueRecord.units_sold).label("units"),
        )
        .where(RevenueRecord.period_start >= start_date)
        .group_by(RevenueRecord.app_id)
    )
    rows = result.all()

    by_game = []
    total_gross = 0
    total_net = 0
    total_units = 0

    for row in rows:
        # Get game name
        game_result = await db.execute(
            select(Game.name).where(Game.app_id == row.app_id)
        )
        name = game_result.scalar_one_or_none() or f"App {row.app_id}"

        by_game.append({
            "app_id": row.app_id,
            "name": name,
            "gross_cents": row.gross or 0,
            "net_cents": row.net or 0,
            "units": row.units or 0,
        })
        total_gross += row.gross or 0
        total_net += row.net or 0
        total_units += row.units or 0

    return RevenueSummaryResponse(
        total_gross_cents=total_gross,
        total_net_cents=total_net,
        total_units=total_units,
        period_start=start_date,
        period_end=date.today(),
        by_game=sorted(by_game, key=lambda x: x["net_cents"], reverse=True),
    )


@router.get("/{app_id}", response_model=GameRevenueResponse)
async def get_game_revenue(
    app_id: int,
    period: str = Query("90d", regex="^\\d+d$"),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get revenue for a specific game."""
    days = int(period.rstrip("d"))
    start_date = date.today() - timedelta(days=days)

    # Get game
    game_result = await db.execute(
        select(Game).where(Game.app_id == app_id)
    )
    game = game_result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get revenue records
    result = await db.execute(
        select(RevenueRecord)
        .where(RevenueRecord.app_id == app_id)
        .where(RevenueRecord.period_start >= start_date)
        .order_by(RevenueRecord.period_start.asc())
    )
    records = result.scalars().all()

    periods = []
    total_gross = 0
    total_net = 0
    total_units = 0

    for record in records:
        periods.append({
            "period_start": record.period_start.isoformat(),
            "period_end": record.period_end.isoformat(),
            "period_type": record.period_type,
            "gross_cents": record.gross_revenue_cents or 0,
            "net_cents": record.net_revenue_cents or 0,
            "units": record.units_sold or 0,
            "refunds": record.refunds or 0,
        })
        total_gross += record.gross_revenue_cents or 0
        total_net += record.net_revenue_cents or 0
        total_units += record.units_sold or 0

    return GameRevenueResponse(
        app_id=app_id,
        name=game.name,
        total_gross_cents=total_gross,
        total_net_cents=total_net,
        total_units=total_units,
        periods=periods,
    )


@router.post("/upload")
async def upload_revenue_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Upload a Steamworks revenue CSV for manual import."""
    from app.collectors.partner import RevenueImporter
    from sqlalchemy.dialects.postgresql import insert

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    csv_content = content.decode("utf-8")

    try:
        records = RevenueImporter.parse_steamworks_csv(csv_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    imported = 0
    for record in records:
        # Get game_id
        game_result = await db.execute(
            select(Game.id).where(Game.app_id == record["app_id"])
        )
        game_id = game_result.scalar_one_or_none()

        stmt = insert(RevenueRecord).values(
            game_id=game_id,
            app_id=record["app_id"],
            period_start=record["period_start"],
            period_end=record["period_end"],
            period_type="monthly",
            gross_revenue_cents=record["gross_revenue_cents"],
            net_revenue_cents=record["net_revenue_cents"],
            units_sold=record["units_sold"],
            refunds=record["refunds"],
            source="csv_upload",
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_revenue_period",
            set_={
                "gross_revenue_cents": stmt.excluded.gross_revenue_cents,
                "net_revenue_cents": stmt.excluded.net_revenue_cents,
                "units_sold": stmt.excluded.units_sold,
                "refunds": stmt.excluded.refunds,
            }
        )
        await db.execute(stmt)
        imported += 1

    await db.commit()

    return {"imported": imported, "message": f"Successfully imported {imported} revenue records"}
