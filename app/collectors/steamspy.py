"""SteamSpy data collector."""
import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import Game, GameSnapshot
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SteamSpyCollector(BaseCollector):
    """Collect game stats from SteamSpy API."""

    name = "steamspy"
    rate_limit_delay = 1.2  # SteamSpy is rate-limited

    STEAMSPY_BASE = "https://steamspy.com/api.php"

    async def collect(self) -> int:
        """Collect stats for all portfolio games."""
        await self.start_run()
        records = 0
        error = None

        try:
            app_ids = settings.portfolio_app_ids
            if not app_ids:
                logger.warning("No portfolio app IDs configured")
                return 0

            for app_id in app_ids:
                try:
                    await self._collect_game(app_id)
                    records += 1
                except Exception as e:
                    logger.error(f"Error collecting app {app_id}: {e}")

                await asyncio.sleep(self.rate_limit_delay)

        except Exception as e:
            error = str(e)
            logger.error(f"Collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _collect_game(self, app_id: int):
        """Collect data for a single game."""
        # Fetch from SteamSpy
        data = await self.fetch_json(
            self.STEAMSPY_BASE,
            params={"request": "appdetails", "appid": app_id}
        )

        if not data or "name" not in data:
            logger.warning(f"No data for app {app_id}")
            return

        # Ensure game exists in our database
        game = await self._ensure_game(app_id, data)

        # Parse owners range
        owners_min, owners_max = self._parse_owners(data.get("owners", "0 .. 0"))

        # Calculate review score
        positive = data.get("positive", 0)
        negative = data.get("negative", 0)
        total = positive + negative
        review_score = round((positive / total) * 100) if total > 0 else 0

        # Create snapshot
        snapshot_data = {
            "game_id": game.id,
            "app_id": app_id,
            "owners_min": owners_min,
            "owners_max": owners_max,
            "ccu": data.get("ccu", 0),
            "players_2weeks": data.get("players_2weeks", 0),
            "avg_playtime_minutes": data.get("average_forever", 0),
            "median_playtime_minutes": data.get("median_forever", 0),
            "avg_playtime_2weeks_minutes": data.get("average_2weeks", 0),
            "reviews_positive": positive,
            "reviews_negative": negative,
            "review_score": review_score,
            "price_cents": int(data.get("price", "0") or "0"),
            "discount_percent": int(data.get("discount", "0") or "0"),
            "snapshot_date": date.today(),
        }

        # Upsert snapshot (update if exists for today)
        stmt = insert(GameSnapshot).values(**snapshot_data)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_game_snapshot_date",
            set_={
                "owners_min": stmt.excluded.owners_min,
                "owners_max": stmt.excluded.owners_max,
                "ccu": stmt.excluded.ccu,
                "players_2weeks": stmt.excluded.players_2weeks,
                "avg_playtime_minutes": stmt.excluded.avg_playtime_minutes,
                "median_playtime_minutes": stmt.excluded.median_playtime_minutes,
                "reviews_positive": stmt.excluded.reviews_positive,
                "reviews_negative": stmt.excluded.reviews_negative,
                "review_score": stmt.excluded.review_score,
                "price_cents": stmt.excluded.price_cents,
                "discount_percent": stmt.excluded.discount_percent,
            }
        )
        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(f"Collected snapshot for {data.get('name')} (CCU: {data.get('ccu', 0)})")

    async def _ensure_game(self, app_id: int, data: dict[str, Any]) -> Game:
        """Ensure game exists in database, create if not."""
        result = await self.db.execute(
            select(Game).where(Game.app_id == app_id)
        )
        game = result.scalar_one_or_none()

        if not game:
            # Parse tags
            tags = list(data.get("tags", {}).keys()) if data.get("tags") else []

            game = Game(
                app_id=app_id,
                name=data.get("name", f"Unknown ({app_id})"),
                developer=data.get("developer"),
                publisher=data.get("publisher"),
                price_cents=int(data.get("initialprice", "0") or "0"),
                tags=tags[:20],  # Limit tags
                genres=data.get("genre", "").split(", ") if data.get("genre") else [],
                is_portfolio=app_id in settings.portfolio_app_ids,
            )
            self.db.add(game)
            await self.db.flush()
            logger.info(f"Created game record for {game.name}")

        return game

    def _parse_owners(self, owners_str: str) -> tuple[int, int]:
        """Parse owners string like '100,000 .. 200,000' to (min, max)."""
        try:
            parts = owners_str.replace(",", "").split(" .. ")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
        return 0, 0

    async def collect_genre(self, genre: str) -> list[dict]:
        """Collect top games for a specific genre/tag."""
        data = await self.fetch_json(
            self.STEAMSPY_BASE,
            params={"request": "tag", "tag": genre}
        )

        if not data:
            return []

        games = []
        for app_id, game_data in data.items():
            games.append({
                "app_id": int(app_id),
                "name": game_data.get("name"),
                "ccu": game_data.get("ccu", 0),
                "owners": game_data.get("owners"),
                "positive": game_data.get("positive", 0),
                "negative": game_data.get("negative", 0),
            })

        return sorted(games, key=lambda x: x["ccu"], reverse=True)
