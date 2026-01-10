"""Steam Store API collector."""
import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import TopSellersSnapshot, NewRelease
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SteamStoreCollector(BaseCollector):
    """Collect data from Steam Store API."""

    name = "steam_store"
    rate_limit_delay = 0.5

    STORE_BASE = "https://store.steampowered.com/api"

    async def collect(self) -> int:
        """Collect market data from Steam Store."""
        await self.start_run()
        records = 0
        error = None

        try:
            # Collect featured/top sellers
            records += await self._collect_featured()
            await asyncio.sleep(self.rate_limit_delay)

            # Collect new releases
            records += await self._collect_new_releases()

        except Exception as e:
            error = str(e)
            logger.error(f"Collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _collect_featured(self) -> int:
        """Collect featured categories (specials, top sellers, etc.)."""
        data = await self.fetch_json(f"{self.STORE_BASE}/featuredcategories/")

        if not data:
            return 0

        records = 0
        today = date.today()

        # Process each category
        categories = [
            ("specials", "specials"),
            ("top_sellers", "top_sellers"),
            ("new_releases", "new_releases"),
            ("coming_soon", "coming_soon"),
        ]

        for key, category_name in categories:
            if key in data and "items" in data[key]:
                items = data[key]["items"]
                rankings = [
                    {
                        "rank": idx + 1,
                        "app_id": item.get("id"),
                        "name": item.get("name"),
                        "price_cents": item.get("final_price", 0),
                        "discount": item.get("discount_percent", 0),
                    }
                    for idx, item in enumerate(items[:50])  # Top 50
                ]

                stmt = insert(TopSellersSnapshot).values(
                    snapshot_date=today,
                    category=category_name,
                    rankings=rankings,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_topsellers_snapshot_date",
                    set_={"rankings": stmt.excluded.rankings}
                )
                await self.db.execute(stmt)
                records += 1

        await self.db.commit()
        logger.info(f"Collected {records} category snapshots")
        return records

    async def _collect_new_releases(self) -> int:
        """Track new indie releases."""
        # This could be expanded to scrape the new releases page
        # For now, we use the featured categories new_releases
        return 0

    async def get_app_details(self, app_id: int) -> dict[str, Any] | None:
        """Get detailed info for a specific app."""
        data = await self.fetch_json(
            f"{self.STORE_BASE}/appdetails",
            params={"appids": app_id}
        )

        if data and str(app_id) in data:
            app_data = data[str(app_id)]
            if app_data.get("success"):
                return app_data.get("data")

        return None

    async def get_reviews(self, app_id: int) -> dict[str, Any] | None:
        """Get review summary for an app."""
        data = await self.fetch_json(
            f"{self.STORE_BASE}/appreviews/{app_id}",
            params={
                "json": 1,
                "language": "all",
                "purchase_type": "all",
            }
        )

        if data and data.get("success"):
            return data.get("query_summary")

        return None
