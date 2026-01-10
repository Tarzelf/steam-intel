"""Steam Partner API collector (requires IP whitelist)."""
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import RevenueRecord
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SteamPartnerCollector(BaseCollector):
    """Collect revenue data from Steam Partner API.

    NOTE: This requires your server IP to be whitelisted by Valve.
    Contact your Steamworks representative to whitelist your VPS IP.
    """

    name = "steam_partner"
    rate_limit_delay = 1.0

    PARTNER_BASE = "https://partner.steam-api.com"

    async def collect(self) -> int:
        """Collect revenue data for portfolio games."""
        if not settings.steam_partner_key:
            logger.warning("No Steam Partner API key configured, skipping")
            return 0

        await self.start_run()
        records = 0
        error = None

        try:
            # Test API access first
            if not await self._test_access():
                logger.error("Partner API access denied - IP may not be whitelisted")
                error = "IP not whitelisted"
                return 0

            # Collect for each portfolio game
            for app_id in settings.portfolio_app_ids:
                try:
                    count = await self._collect_game_revenue(app_id)
                    records += count
                except Exception as e:
                    logger.error(f"Error collecting revenue for {app_id}: {e}")

        except Exception as e:
            error = str(e)
            logger.error(f"Partner collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _test_access(self) -> bool:
        """Test if we have Partner API access."""
        # Try a simple endpoint
        data = await self.fetch_json(
            f"{self.PARTNER_BASE}/ISteamEconomy/GetAssetPrices/v1/",
            params={
                "key": settings.steam_partner_key,
                "appid": 730,  # CS2 as test
            }
        )
        return data is not None and "result" in data

    async def _collect_game_revenue(self, app_id: int) -> int:
        """Collect revenue for a specific game.

        NOTE: The actual Partner API endpoints for financial data require
        additional permissions. This is a placeholder for the structure.
        Real implementation would use ISteamMicroTxn or financial reports API.
        """
        # Placeholder - real implementation would call actual revenue endpoints
        # Steam's financial API is not publicly documented

        logger.info(f"Revenue collection for {app_id} - placeholder")
        return 0

    async def get_asset_prices(self, app_id: int) -> dict[str, Any] | None:
        """Get asset/item prices for a game (if it has marketplace items)."""
        if not settings.steam_partner_key:
            return None

        return await self.fetch_json(
            f"{self.PARTNER_BASE}/ISteamEconomy/GetAssetPrices/v1/",
            params={
                "key": settings.steam_partner_key,
                "appid": app_id,
            }
        )


class RevenueImporter:
    """Import revenue from CSV/manual upload.

    Since Steam Partner API financial data requires special access,
    this class handles manual CSV imports from Steamworks reports.
    """

    @staticmethod
    def parse_steamworks_csv(csv_content: str) -> list[dict]:
        """Parse a Steamworks financial report CSV.

        Expected format from Steamworks -> Financial Reports -> Download
        """
        import csv
        from io import StringIO

        records = []
        reader = csv.DictReader(StringIO(csv_content))

        for row in reader:
            # Adapt these field names based on actual Steamworks CSV format
            records.append({
                "app_id": int(row.get("App ID", 0)),
                "period_start": row.get("Period Start"),
                "period_end": row.get("Period End"),
                "gross_revenue_cents": int(float(row.get("Gross Revenue", 0)) * 100),
                "net_revenue_cents": int(float(row.get("Net Revenue", 0)) * 100),
                "units_sold": int(row.get("Units Sold", 0)),
                "refunds": int(row.get("Refunds", 0)),
            })

        return records
