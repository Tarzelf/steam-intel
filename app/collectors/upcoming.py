"""Upcoming releases collector for competitive intelligence."""
import asyncio
import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import UpcomingRelease

logger = logging.getLogger(__name__)


class UpcomingReleasesCollector(BaseCollector):
    """Track upcoming Steam releases for competitive intelligence."""

    name = "upcoming_releases_collector"
    rate_limit_delay = 0.5

    STEAM_STORE_BASE = "https://store.steampowered.com/api"
    STEAM_FEATURED_URL = "https://store.steampowered.com/api/featuredcategories/"

    async def collect(self) -> int:
        """Collect upcoming releases from Steam."""
        await self.start_run()
        records = 0
        error = None

        try:
            # Fetch featured categories which includes coming soon
            data = await self.fetch_json(self.STEAM_FEATURED_URL)

            if not data:
                logger.warning("No featured data from Steam")
                return 0

            # Process coming soon section
            coming_soon = data.get("coming_soon", {}).get("items", [])
            logger.info(f"Found {len(coming_soon)} coming soon items")

            for item in coming_soon:
                try:
                    app_id = item.get("id")
                    if not app_id:
                        continue

                    await self._process_upcoming_game(app_id, item)
                    records += 1

                    await asyncio.sleep(self.rate_limit_delay)

                except Exception as e:
                    logger.error(f"Error processing upcoming game {item.get('id')}: {e}")

            # Also fetch from new releases that might be "coming soon"
            # This can be expanded to use Steam's search API

        except Exception as e:
            error = str(e)
            logger.error(f"Upcoming releases collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _process_upcoming_game(self, app_id: int, basic_data: dict):
        """Process a single upcoming game."""
        # Get detailed app info
        details = await self._get_app_details(app_id)

        if not details:
            # Use basic data from featured list
            name = basic_data.get("name", "Unknown")
            price_cents = 0
            if basic_data.get("final_price"):
                price_cents = basic_data.get("final_price", 0)
            elif basic_data.get("original_price"):
                price_cents = basic_data.get("original_price", 0)

            release_data = {
                "app_id": app_id,
                "name": name,
                "price_cents": price_cents,
                "source": "steam_featured",
            }
        else:
            # Extract detailed info
            release_date_info = details.get("release_date", {})
            expected_release = self._parse_release_date(release_date_info)

            genres = [g.get("description") for g in details.get("genres", [])]
            tags = self._extract_tags_from_categories(details.get("categories", []))

            # Price
            price_overview = details.get("price_overview", {})
            price_cents = price_overview.get("initial", 0)
            if not price_cents and details.get("is_free"):
                price_cents = 0

            # Check for demo
            has_demo = details.get("demos") is not None

            # Calculate hype score based on available signals
            hype_score = self._calculate_hype_score(details)

            release_data = {
                "app_id": app_id,
                "name": details.get("name", "Unknown"),
                "developer": details.get("developers", [None])[0] if details.get("developers") else None,
                "publisher": details.get("publishers", [None])[0] if details.get("publishers") else None,
                "expected_release": expected_release,
                "genres": genres if genres else None,
                "tags": tags if tags else None,
                "price_cents": price_cents,
                "has_demo": has_demo,
                "hype_score": hype_score,
                "source": "steam_api",
                "last_updated": datetime.utcnow(),
            }

        # Upsert release
        stmt = insert(UpcomingRelease).values(**release_data)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_upcoming_app",
            set_={k: stmt.excluded[k] for k in release_data.keys() if k != "app_id"}
        )
        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(f"Processed upcoming: {release_data.get('name')} ({app_id})")

    async def _get_app_details(self, app_id: int) -> Optional[dict]:
        """Get detailed app info from Steam Store API."""
        url = f"{self.STEAM_STORE_BASE}/appdetails"
        params = {"appids": app_id, "cc": "us", "l": "english"}

        try:
            data = await self.fetch_json(url, params=params)
            if data and str(app_id) in data:
                app_data = data[str(app_id)]
                if app_data.get("success"):
                    return app_data.get("data")
        except Exception as e:
            logger.debug(f"Could not get details for {app_id}: {e}")

        return None

    def _parse_release_date(self, release_info: dict) -> Optional[date]:
        """Parse release date from Steam's format."""
        if not release_info:
            return None

        date_str = release_info.get("date", "")

        if not date_str or release_info.get("coming_soon"):
            # Try to extract year/quarter from the string
            # Common formats: "Q1 2025", "2025", "Coming Soon", "To be announced"
            import re

            # Look for year
            year_match = re.search(r"20\d{2}", date_str)
            if year_match:
                year = int(year_match.group())
                # Look for quarter
                quarter_match = re.search(r"Q([1-4])", date_str)
                if quarter_match:
                    quarter = int(quarter_match.group(1))
                    month = (quarter - 1) * 3 + 2  # Middle of quarter
                    return date(year, month, 15)
                # Just year - assume mid-year
                return date(year, 6, 15)

            return None

        # Try common date formats
        formats = [
            "%b %d, %Y",  # Jan 15, 2025
            "%d %b, %Y",  # 15 Jan, 2025
            "%B %d, %Y",  # January 15, 2025
            "%Y-%m-%d",   # 2025-01-15
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    def _extract_tags_from_categories(self, categories: list) -> list:
        """Extract meaningful tags from Steam categories."""
        # Steam categories include multiplayer modes, controller support, etc.
        # Filter to gameplay-relevant ones
        relevant_ids = {
            1: "Multi-player",
            2: "Single-player",
            9: "Co-op",
            20: "MMO",
            24: "Local Co-op",
            27: "Cross-Platform",
            36: "Online Co-op",
            37: "Local Multi-player",
            38: "Online PvP",
        }

        tags = []
        for cat in categories:
            cat_id = cat.get("id")
            if cat_id in relevant_ids:
                tags.append(relevant_ids[cat_id])

        return tags

    def _calculate_hype_score(self, details: dict) -> int:
        """Calculate a hype score based on available signals."""
        score = 50  # Base score

        # Has screenshots/videos = more polished
        if details.get("screenshots"):
            score += 5
        if details.get("movies"):
            score += 10

        # Has demo = confident
        if details.get("demos"):
            score += 15

        # Well-known publisher boost (could be expanded)
        publisher = (details.get("publishers") or [""])[0].lower()
        if publisher in ["devolver digital", "raw fury", "team17", "annapurna interactive"]:
            score += 20

        # Genre bonuses for hot genres
        genres = [g.get("description", "").lower() for g in details.get("genres", [])]
        hot_genres = ["roguelike", "roguelite", "deck builder", "survival", "horror"]
        for genre in genres:
            if any(hot in genre for hot in hot_genres):
                score += 10
                break

        # Cap at 100
        return min(100, score)


async def run_upcoming_collection():
    """Run upcoming releases collection manually.

    python -c "import asyncio; from app.collectors.upcoming import run_upcoming_collection; asyncio.run(run_upcoming_collection())"
    """
    from app.database import async_session_maker

    async with async_session_maker() as session:
        collector = UpcomingReleasesCollector(session)
        await collector.collect()
        print("Upcoming releases collection complete!")
