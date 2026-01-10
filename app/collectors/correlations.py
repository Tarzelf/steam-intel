"""Tag correlation collector for analyzing synergistic tag combinations."""
import asyncio
import logging
import statistics
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import TagCorrelation, GenreGame

logger = logging.getLogger(__name__)

# Interesting tag pairs to analyze for synergies
TAG_PAIRS = [
    # Genre + Mechanic combos
    ("Roguelike", "Deck Building"),
    ("Roguelike", "Action"),
    ("Roguelike", "Bullet Hell"),
    ("Roguelite", "Platformer"),
    ("Souls-like", "Action"),
    ("Souls-like", "Action RPG"),
    ("Metroidvania", "Pixel Graphics"),
    ("Metroidvania", "Action"),

    # Survival combos
    ("Survival", "Crafting"),
    ("Survival", "Horror"),
    ("Survival", "Open World"),
    ("Survival", "Co-op"),

    # Co-op combos
    ("Co-op", "Action"),
    ("Co-op", "Puzzle"),
    ("Co-op", "Horror"),
    ("Local Co-Op", "Platformer"),

    # Strategy combos
    ("Strategy", "Turn-Based"),
    ("Strategy", "City Builder"),
    ("Turn-Based Tactics", "RPG"),

    # Cozy combos
    ("Cozy", "Farming Sim"),
    ("Cozy", "Simulation"),
    ("Cozy", "Management"),

    # Visual style combos
    ("Pixel Graphics", "Platformer"),
    ("Pixel Graphics", "Action"),
    ("Hand-Drawn", "Adventure"),
    ("Anime", "RPG"),
    ("Anime", "Visual Novel"),

    # Theme combos
    ("Horror", "Psychological"),
    ("Horror", "Survival"),
    ("Sci-fi", "Strategy"),
    ("Fantasy", "RPG"),
    ("Cyberpunk", "Action"),
    ("Post-apocalyptic", "Survival"),

    # Emerging combos
    ("Auto Battler", "Strategy"),
    ("Colony Sim", "Survival"),
    ("Tower Defense", "Strategy"),
    ("City Builder", "Simulation"),
]


class TagCorrelationCollector(BaseCollector):
    """Analyze tag co-occurrence patterns for market intelligence."""

    name = "tag_correlation_collector"
    rate_limit_delay = 0.5  # Faster since we're querying local DB

    async def collect(self) -> int:
        """Collect tag correlation data."""
        await self.start_run()
        records = 0
        error = None

        try:
            # Get today's genre games data
            today = date.today()

            # Build a mapping of app_id -> game data with tags
            result = await self.db.execute(
                select(GenreGame).where(GenreGame.snapshot_date == today)
            )
            all_games = result.scalars().all()

            if not all_games:
                logger.warning("No genre games data for today, skipping correlation analysis")
                return 0

            # Build game -> tags mapping
            games_by_id = {}
            for game in all_games:
                if game.app_id not in games_by_id:
                    games_by_id[game.app_id] = {
                        "app_id": game.app_id,
                        "name": game.name,
                        "ccu": game.ccu or 0,
                        "review_score": game.review_score or 0,
                        "price_cents": game.price_cents or 0,
                        "tags": set(game.tags) if game.tags else set(),
                    }
                else:
                    # Merge tags from different genre entries
                    if game.tags:
                        games_by_id[game.app_id]["tags"].update(game.tags)
                    # Update CCU if higher
                    if game.ccu and game.ccu > games_by_id[game.app_id]["ccu"]:
                        games_by_id[game.app_id]["ccu"] = game.ccu

            logger.info(f"Loaded {len(games_by_id)} unique games for correlation analysis")

            # Analyze each tag pair
            for tag_a, tag_b in TAG_PAIRS:
                try:
                    await self._analyze_tag_pair(tag_a, tag_b, games_by_id, today)
                    records += 1
                except Exception as e:
                    logger.error(f"Error analyzing {tag_a} + {tag_b}: {e}")

                await asyncio.sleep(self.rate_limit_delay)

        except Exception as e:
            error = str(e)
            logger.error(f"Tag correlation collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _analyze_tag_pair(
        self,
        tag_a: str,
        tag_b: str,
        games_by_id: dict,
        snapshot_date: date
    ):
        """Analyze co-occurrence of two tags."""
        # Find games with both tags
        common_games = []
        games_with_a = 0
        games_with_b = 0

        for app_id, game in games_by_id.items():
            tags = game["tags"]
            has_a = tag_a in tags or tag_a.lower() in {t.lower() for t in tags}
            has_b = tag_b in tags or tag_b.lower() in {t.lower() for t in tags}

            if has_a:
                games_with_a += 1
            if has_b:
                games_with_b += 1
            if has_a and has_b:
                common_games.append(game)

        if not common_games:
            logger.debug(f"No games with both {tag_a} and {tag_b}")
            return

        # Calculate metrics
        co_occurrence_count = len(common_games)
        combined_ccu = sum(g["ccu"] for g in common_games)

        review_scores = [g["review_score"] for g in common_games if g["review_score"] > 0]
        avg_review_score = int(statistics.mean(review_scores)) if review_scores else 0

        prices = [g["price_cents"] for g in common_games if g["price_cents"] > 0]
        avg_price_cents = int(statistics.mean(prices)) if prices else 0

        # Correlation strength: Jaccard similarity
        min_count = min(games_with_a, games_with_b)
        correlation_strength = co_occurrence_count / min_count if min_count > 0 else 0

        # Top games by CCU
        top_games = sorted(common_games, key=lambda x: x["ccu"], reverse=True)[:5]
        top_games_data = [
            {
                "app_id": g["app_id"],
                "name": g["name"],
                "ccu": g["ccu"],
                "review_score": g["review_score"],
            }
            for g in top_games
        ]

        # Upsert correlation
        correlation_data = {
            "tag_a": tag_a,
            "tag_b": tag_b,
            "snapshot_date": snapshot_date,
            "co_occurrence_count": co_occurrence_count,
            "correlation_strength": correlation_strength,
            "combined_ccu": combined_ccu,
            "avg_review_score": avg_review_score,
            "avg_price_cents": avg_price_cents,
            "top_games": top_games_data,
        }

        stmt = insert(TagCorrelation).values(**correlation_data)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tag_correlation_date",
            set_={k: stmt.excluded[k] for k in correlation_data.keys() if k not in ["tag_a", "tag_b", "snapshot_date"]}
        )
        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(f"Analyzed {tag_a} + {tag_b}: {co_occurrence_count} games, {combined_ccu} CCU")


async def run_correlation_analysis():
    """Run correlation analysis manually.

    python -c "import asyncio; from app.collectors.correlations import run_correlation_analysis; asyncio.run(run_correlation_analysis())"
    """
    from app.database import async_session_maker

    async with async_session_maker() as session:
        collector = TagCorrelationCollector(session)
        await collector.collect()
        print("Tag correlation analysis complete!")
