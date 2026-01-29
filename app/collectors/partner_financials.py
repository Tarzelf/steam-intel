"""Steam Partner Financials API Collector.

Implements IPartnerFinancialsService to fetch actual revenue data.
"""
import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, delete

from app.collectors.base import BaseCollector
from app.models import RevenueRecord, Game
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PartnerFinancialsCollector(BaseCollector):
    """Collect revenue data from Steam IPartnerFinancialsService."""

    name = "partner_financials"
    rate_limit_delay = 0.2  # 200ms between requests

    PARTNER_BASE = "https://partner.steam-api.com"

    def __init__(self, db: AsyncSession):
        super().__init__(db)  # Pass db to base class
        self.db = db
        self._highwatermark: str = "0"
        self._app_id_to_game: dict[int, tuple[str, str]] = {}

    async def collect(self, full_sync: bool = False, days: int | None = None) -> dict:
        """Collect revenue data from Steam Partner API."""
        if not settings.steam_partner_key:
            logger.warning("No Steam Partner API key configured")
            return {"success": False, "error": "No API key configured"}

        await self.start_run()

        result = {
            "success": True,
            "dates_processed": 0,
            "records_upserted": 0,
            "errors": [],
            "new_highwatermark": self._highwatermark,
        }

        try:
            await self._load_game_mappings()
            logger.info(f"Loaded {len(self._app_id_to_game)} game mappings")

            if not full_sync:
                self._highwatermark = await self._load_highwatermark()
                logger.info(f"Starting from highwatermark: {self._highwatermark}")
            else:
                self._highwatermark = "0"
                logger.info("Full sync - starting from beginning")

            changed_dates = await self._get_changed_dates()
            logger.info(f"Found {len(changed_dates['dates'])} dates with changes")

            if not changed_dates["dates"]:
                await self.complete_run(0, None)
                return result

            dates_to_sync = changed_dates["dates"]
            if days:
                cutoff_date = (date.today() - timedelta(days=days)).isoformat().replace("-", "/")
                dates_to_sync = [d for d in dates_to_sync if d >= cutoff_date]
                logger.info(f"Filtered to {len(dates_to_sync)} dates (last {days} days)")

            for i, sync_date in enumerate(dates_to_sync):
                try:
                    logger.info(f"[{i+1}/{len(dates_to_sync)}] Processing {sync_date}...")
                    records = await self._collect_date(sync_date)
                    result["records_upserted"] += records
                    result["dates_processed"] += 1
                except Exception as e:
                    error_msg = f"{sync_date}: {str(e)}"
                    result["errors"].append(error_msg)
                    logger.error(f"Error processing {sync_date}: {e}")
                    await self.db.rollback()

                await asyncio.sleep(self.rate_limit_delay)

            new_hwm = changed_dates["highwatermark"]
            await self._save_highwatermark(new_hwm)
            result["new_highwatermark"] = new_hwm

            await self.complete_run(result["records_upserted"], None)

        except Exception as e:
            result["success"] = False
            result["errors"].append(str(e))
            logger.error(f"Collection failed: {e}")
            await self.db.rollback()
            await self.complete_run(0, str(e))

        return result

    async def _load_game_mappings(self):
        """Load mapping of Steam App ID to internal game ID."""
        query = select(Game.id, Game.app_id, Game.name).where(Game.app_id.isnot(None))
        result = await self.db.execute(query)

        self._app_id_to_game = {}
        for row in result.all():
            self._app_id_to_game[row.app_id] = (str(row.id), row.name)

        logger.info(f"Mapped {len(self._app_id_to_game)} games to Steam App IDs")

    async def _load_highwatermark(self) -> str:
        """Load last sync highwatermark from database."""
        return "0"

    async def _save_highwatermark(self, highwatermark: str):
        """Save highwatermark for next sync."""
        logger.info(f"Highwatermark to save: {highwatermark}")

    async def _get_changed_dates(self) -> dict:
        """Get dates with changed data from Steam API."""
        url = f"{self.PARTNER_BASE}/IPartnerFinancialsService/GetChangedDatesForPartner/v001/"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params={
                "key": settings.steam_partner_key,
                "highwatermark": self._highwatermark,
            })
            response.raise_for_status()
            data = response.json()

        return {
            "dates": data.get("response", {}).get("dates", []),
            "highwatermark": data.get("response", {}).get("result_highwatermark", self._highwatermark),
        }

    async def _collect_date(self, sync_date: str) -> int:
        """Collect and store revenue for a specific date."""
        sales_data = await self._get_detailed_sales(sync_date)

        if not sales_data["results"]:
            return 0

        aggregates = self._aggregate_by_app(sales_data)

        records_saved = 0
        for app_id, agg in aggregates.items():
            game_mapping = self._app_id_to_game.get(app_id)
            if not game_mapping:
                continue

            game_id, game_name = game_mapping
            period_date = date.fromisoformat(sync_date.replace("/", "-"))

            await self.db.execute(
                delete(RevenueRecord).where(
                    RevenueRecord.game_id == game_id,
                    RevenueRecord.period_start == period_date,
                )
            )

            stmt = pg_insert(RevenueRecord).values(
                game_id=game_id,
                app_id=app_id,
                period_start=period_date,
                period_end=period_date,
                period_type="daily",
                gross_revenue_cents=int(agg["gross_revenue"] * 100),
                net_revenue_cents=int(agg["net_revenue"] * 100),
                units_sold=agg["units_sold"],
                refunds=agg["units_returned"],
                source="partner_api",
                raw_data={
                    "tax_usd": agg["tax"],
                    "by_country": agg["by_country"],
                    "by_platform": agg["by_platform"],
                },
            )

            await self.db.execute(stmt)
            records_saved += 1

        await self.db.commit()
        return records_saved

    async def _get_detailed_sales(self, sync_date: str) -> dict:
        """Get detailed sales data for a date, handling pagination."""
        url = f"{self.PARTNER_BASE}/IPartnerFinancialsService/GetDetailedSales/v001/"

        all_results = []
        app_info = {}
        country_info = {}

        highwatermark_id = "0"
        iterations = 0
        max_iterations = 1000

        async with httpx.AsyncClient(timeout=30.0) as client:
            while iterations < max_iterations:
                iterations += 1

                response = await client.get(url, params={
                    "key": settings.steam_partner_key,
                    "date": sync_date,
                    "highwatermark_id": highwatermark_id,
                })
                response.raise_for_status()
                data = response.json().get("response", {})

                results = data.get("results", [])
                if results:
                    all_results.extend(results)

                for app in data.get("app_info", []):
                    app_info[app["appid"]] = app["app_name"]

                for country in data.get("country_info", []):
                    country_info[country["country_code"]] = country

                max_id = data.get("max_id", "0")
                if max_id == highwatermark_id:
                    break

                highwatermark_id = max_id
                await asyncio.sleep(self.rate_limit_delay)

        return {
            "results": all_results,
            "app_info": app_info,
            "country_info": country_info,
        }

    def _aggregate_by_app(self, sales_data: dict) -> dict[int, dict]:
        """Aggregate sales results by app ID."""
        aggregates: dict[int, dict] = {}

        for r in sales_data["results"]:
            if r.get("package_sale_type") == "Retail":
                continue

            app_id = r.get("primary_appid") or r.get("appid")
            if not app_id:
                continue

            if app_id not in aggregates:
                aggregates[app_id] = {
                    "gross_revenue": 0.0,
                    "net_revenue": 0.0,
                    "tax": 0.0,
                    "units_sold": 0,
                    "units_returned": 0,
                    "by_country": {},
                    "by_platform": {},
                }

            agg = aggregates[app_id]

            gross = float(r.get("gross_sales_usd", "0"))
            net = float(r.get("net_sales_usd", "0"))
            tax = float(r.get("net_tax_usd", "0"))
            sold = r.get("gross_units_sold", 0)
            returned = abs(r.get("gross_units_returned", 0))

            agg["gross_revenue"] += gross
            agg["net_revenue"] += net
            agg["tax"] += tax
            agg["units_sold"] += sold
            agg["units_returned"] += returned

            country = r.get("country_code", "XX")
            if country not in agg["by_country"]:
                agg["by_country"][country] = {"revenue": 0.0, "units": 0}
            agg["by_country"][country]["revenue"] += gross
            agg["by_country"][country]["units"] += sold

            platform = r.get("platform", "Unknown")
            if platform not in agg["by_platform"]:
                agg["by_platform"][platform] = 0
            agg["by_platform"][platform] += sold

        return aggregates


async def run_partner_sync(db: AsyncSession, full_sync: bool = False, days: int | None = None) -> dict:
    """Run partner financials sync."""
    collector = PartnerFinancialsCollector(db)
    return await collector.collect(full_sync=full_sync, days=days)
