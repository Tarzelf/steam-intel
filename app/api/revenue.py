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


# ============================================================
# Partner Financials Sync Endpoints
# ============================================================

class SyncRequest(BaseModel):
    """Request to trigger a sync."""
    days: Optional[int] = None
    full_sync: bool = False


class SyncResponse(BaseModel):
    """Response from sync."""
    success: bool
    dates_processed: int
    records_upserted: int
    errors: list[str]
    new_highwatermark: str


class SyncStatusResponse(BaseModel):
    """Sync status."""
    last_sync_at: Optional[str] = None
    last_sync_status: Optional[str] = None
    configured_games: int
    total_revenue_records: int


@router.post("/sync", response_model=SyncResponse)
async def sync_revenue(
    request: SyncRequest,
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Trigger Steam Partner Financials sync."""
    from app.collectors.partner_financials import run_partner_sync

    result = await run_partner_sync(
        db,
        full_sync=request.full_sync,
        days=request.days,
    )

    return SyncResponse(
        success=result.get("success", False),
        dates_processed=result.get("dates_processed", 0),
        records_upserted=result.get("records_upserted", 0),
        errors=result.get("errors", []),
        new_highwatermark=result.get("new_highwatermark", "0"),
    )


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Get sync status."""
    from app.models import CollectionRun

    # Last sync
    last_run = await db.execute(
        select(CollectionRun)
        .where(CollectionRun.collector_name == "partner_financials")
        .order_by(CollectionRun.completed_at.desc())
        .limit(1)
    )
    run = last_run.scalar_one_or_none()

    # Counts
    games_count = await db.execute(
        select(func.count()).where(Game.app_id.isnot(None))
    )
    records_count = await db.execute(
        select(func.count()).select_from(RevenueRecord)
        .where(RevenueRecord.source == "partner_api")
    )

    return SyncStatusResponse(
        last_sync_at=run.completed_at.isoformat() if run and run.completed_at else None,
        last_sync_status="success" if run and not run.error_message else "error" if run else None,
        configured_games=games_count.scalar() or 0,
        total_revenue_records=records_count.scalar() or 0,
    )


@router.post("/backfill")
async def backfill_revenue(
    db: AsyncSession = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    """Run full historical backfill."""
    from app.collectors.partner_financials import run_partner_sync
    return await run_partner_sync(db, full_sync=True)
