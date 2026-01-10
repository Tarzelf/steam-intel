"""Genre/Tag trend collector."""
import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import GenreSnapshot, GenreScore

logger = logging.getLogger(__name__)

# Key indie-relevant genres/tags to track
TRACKED_GENRES = [
    # Core genres
    "Indie",
    "Action",
    "Adventure",
    "RPG",
    "Strategy",
    "Simulation",
    "Casual",
    "Puzzle",

    # Hot sub-genres
    "Roguelike",
    "Roguelite",
    "Metroidvania",
    "Souls-like",
    "Deck Building",
    "Auto Battler",
    "Bullet Hell",
    "Survival",
    "Horror",
    "Cozy",
    "Farming Sim",
    "City Builder",
    "Colony Sim",
    "Tower Defense",
    "Platformer",
    "Turn-Based Tactics",
    "JRPG",
    "Action RPG",
    "Hack and Slash",
    "Beat 'em up",

    # Visual/Style
    "Pixel Graphics",
    "Retro",
    "Hand-Drawn",
    "Anime",

    # Multiplayer
    "Co-op",
    "Local Co-Op",
    "Online Co-Op",
    "PvP",

    # Themes
    "Sci-fi",
    "Fantasy",
    "Post-apocalyptic",
    "Cyberpunk",
    "Lovecraftian",
]


class GenreCollector(BaseCollector):
    """Collect genre/tag trend data from SteamSpy."""

    name = "genre_collector"
    rate_limit_delay = 1.5  # SteamSpy rate limit

    STEAMSPY_BASE = "https://steamspy.com/api.php"

    async def collect(self) -> int:
        """Collect stats for all tracked genres."""
        await self.start_run()
        records = 0
        error = None

        try:
            for genre in TRACKED_GENRES:
                try:
                    await self._collect_genre(genre)
                    records += 1
                    logger.info(f"Collected genre: {genre}")
                except Exception as e:
                    logger.error(f"Error collecting genre {genre}: {e}")

                await asyncio.sleep(self.rate_limit_delay)

            # Calculate genre scores after collection
            await self._calculate_genre_scores()

        except Exception as e:
            error = str(e)
            logger.error(f"Genre collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _collect_genre(self, genre: str):
        """Collect data for a single genre/tag."""
        data = await self.fetch_json(
            self.STEAMSPY_BASE,
            params={"request": "tag", "tag": genre}
        )

        if not data:
            logger.warning(f"No data for genre: {genre}")
            return

        # Process games in this genre
        games = list(data.values())

        # Calculate aggregates
        total_ccu = sum(g.get("ccu", 0) for g in games)
        game_count = len(games)
        avg_ccu = total_ccu // game_count if game_count > 0 else 0

        # Calculate average review score
        review_scores = []
        for g in games:
            pos = g.get("positive", 0)
            neg = g.get("negative", 0)
            total = pos + neg
            if total > 0:
                review_scores.append(round((pos / total) * 100))

        avg_review_score = sum(review_scores) // len(review_scores) if review_scores else 0

        # Estimate total owners
        total_owners = 0
        for g in games:
            owners_str = g.get("owners", "0 .. 0")
            min_owners, max_owners = self._parse_owners(owners_str)
            total_owners += (min_owners + max_owners) // 2

        # Get top games by CCU
        top_games = sorted(games, key=lambda x: x.get("ccu", 0), reverse=True)[:10]
        top_games_data = [
            {
                "app_id": int(g.get("appid", 0)),
                "name": g.get("name", "Unknown"),
                "ccu": g.get("ccu", 0),
                "owners": g.get("owners", "Unknown"),
                "positive": g.get("positive", 0),
                "negative": g.get("negative", 0),
            }
            for g in top_games
        ]

        # Upsert genre snapshot
        snapshot_data = {
            "genre": genre,
            "snapshot_date": date.today(),
            "game_count": game_count,
            "total_ccu": total_ccu,
            "avg_ccu": avg_ccu,
            "total_owners_estimate": total_owners,
            "avg_review_score": avg_review_score,
            "top_games": top_games_data,
        }

        stmt = insert(GenreSnapshot).values(**snapshot_data)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_genre_snapshot_date",
            set_={
                "game_count": stmt.excluded.game_count,
                "total_ccu": stmt.excluded.total_ccu,
                "avg_ccu": stmt.excluded.avg_ccu,
                "total_owners_estimate": stmt.excluded.total_owners_estimate,
                "avg_review_score": stmt.excluded.avg_review_score,
                "top_games": stmt.excluded.top_games,
            }
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def _calculate_genre_scores(self):
        """Calculate hotness/fitness scores for each genre."""
        today = date.today()

        # Get today's snapshots
        result = await self.db.execute(
            select(GenreSnapshot).where(GenreSnapshot.snapshot_date == today)
        )
        snapshots = {s.genre: s for s in result.scalars().all()}

        if not snapshots:
            return

        # Calculate relative scores
        max_ccu = max(s.total_ccu or 0 for s in snapshots.values())
        max_games = max(s.game_count or 0 for s in snapshots.values())

        for genre, snapshot in snapshots.items():
            # Hotness: based on total CCU (player interest)
            hotness = min(100, int((snapshot.total_ccu or 0) / max(max_ccu, 1) * 100)) if max_ccu > 0 else 50

            # Saturation: based on game count (competition)
            saturation = min(100, int((snapshot.game_count or 0) / max(max_games, 1) * 100)) if max_games > 0 else 50

            # Success rate: based on average review score
            success_rate = snapshot.avg_review_score or 50

            # Timing score: inverse of saturation (less saturated = better timing)
            timing = 100 - saturation

            # Overall score: weighted average
            overall = int((hotness * 0.4) + (success_rate * 0.3) + (timing * 0.3))

            # Recommendation
            if overall >= 70 and saturation < 50:
                recommendation = "hot"
            elif overall >= 60:
                recommendation = "growing"
            elif saturation >= 70:
                recommendation = "saturated"
            else:
                recommendation = "niche"

            score_data = {
                "genre": genre,
                "score_date": today,
                "hotness_score": hotness,
                "saturation_score": saturation,
                "success_rate_score": success_rate,
                "timing_score": timing,
                "overall_score": overall,
                "recommendation": recommendation,
            }

            stmt = insert(GenreScore).values(**score_data)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_genre_score_date",
                set_={
                    "hotness_score": stmt.excluded.hotness_score,
                    "saturation_score": stmt.excluded.saturation_score,
                    "success_rate_score": stmt.excluded.success_rate_score,
                    "timing_score": stmt.excluded.timing_score,
                    "overall_score": stmt.excluded.overall_score,
                    "recommendation": stmt.excluded.recommendation,
                }
            )
            await self.db.execute(stmt)

        await self.db.commit()
        logger.info(f"Calculated scores for {len(snapshots)} genres")

    def _parse_owners(self, owners_str: str) -> tuple[int, int]:
        """Parse owners string like '100,000 .. 200,000' to (min, max)."""
        try:
            parts = owners_str.replace(",", "").split(" .. ")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
        return 0, 0


async def backfill_genres():
    """One-time backfill of genre data.

    Run this manually to populate initial data:
    python -c "import asyncio; from app.collectors.genres import backfill_genres; asyncio.run(backfill_genres())"
    """
    from app.database import async_session_maker

    async with async_session_maker() as session:
        collector = GenreCollector(session)
        await collector.collect()
        print("Genre backfill complete!")
