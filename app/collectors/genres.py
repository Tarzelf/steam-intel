"""Genre/Tag trend collector with enhanced market intelligence."""
import asyncio
import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Any
from collections import Counter

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.collectors.base import BaseCollector
from app.models import GenreSnapshot, GenreScore, GenreGame

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
    """Collect genre/tag trend data from SteamSpy with enhanced metrics."""

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
                    await self._collect_genre_enhanced(genre)
                    records += 1
                    logger.info(f"Collected genre: {genre}")
                except Exception as e:
                    logger.error(f"Error collecting genre {genre}: {e}")

                await asyncio.sleep(self.rate_limit_delay)

            # Calculate genre scores after collection
            await self._calculate_genre_scores_enhanced()

        except Exception as e:
            error = str(e)
            logger.error(f"Genre collection failed: {e}")
        finally:
            await self.complete_run(records, error)

        return records

    async def _collect_genre_enhanced(self, genre: str):
        """Collect enhanced data for a single genre/tag."""
        data = await self.fetch_json(
            self.STEAMSPY_BASE,
            params={"request": "tag", "tag": genre}
        )

        if not data:
            logger.warning(f"No data for genre: {genre}")
            return

        # Process games in this genre
        games = list(data.values())
        today = date.today()

        # Calculate core aggregates
        total_ccu = sum(g.get("ccu", 0) for g in games)
        game_count = len(games)
        avg_ccu = total_ccu // game_count if game_count > 0 else 0

        # Calculate average review score
        review_scores = []
        review_counts = []
        for g in games:
            pos = g.get("positive", 0)
            neg = g.get("negative", 0)
            total = pos + neg
            if total > 0:
                review_scores.append(round((pos / total) * 100))
                review_counts.append(total)

        avg_review_score = sum(review_scores) // len(review_scores) if review_scores else 0
        median_review_count = int(statistics.median(review_counts)) if review_counts else 0

        # Estimate total owners
        total_owners = 0
        for g in games:
            owners_str = g.get("owners", "0 .. 0")
            min_owners, max_owners = self._parse_owners(owners_str)
            total_owners += (min_owners + max_owners) // 2

        # === ENHANCED METRICS ===

        # Pricing analytics
        prices = []
        for g in games:
            price = g.get("price", "0")
            if isinstance(price, str):
                price = int(price) if price.isdigit() else 0
            prices.append(price)

        prices_nonzero = [p for p in prices if p > 0]
        avg_price_cents = int(statistics.mean(prices_nonzero)) if prices_nonzero else 0
        median_price_cents = int(statistics.median(prices_nonzero)) if prices_nonzero else 0
        price_distribution = self._calculate_price_distribution(prices)

        # Release velocity (approximate from SteamSpy data)
        # Note: SteamSpy doesn't always have accurate release dates, so we estimate
        releases_last_30d = 0
        releases_last_90d = 0
        game_ages = []

        # Early Access count
        early_access_count = 0

        # Tag co-occurrence
        all_tags = []

        for g in games:
            # Check tags for Early Access indicator
            tags = g.get("tags", {})
            if isinstance(tags, dict):
                tag_names = list(tags.keys())
                all_tags.extend(tag_names)
                if "Early Access" in tag_names:
                    early_access_count += 1

        # Get top co-occurring tags (excluding the current genre)
        tag_counter = Counter(all_tags)
        if genre in tag_counter:
            del tag_counter[genre]
        top_tags = [{"tag": tag, "count": count} for tag, count in tag_counter.most_common(10)]

        early_access_pct = round((early_access_count / game_count) * 100) if game_count > 0 else 0

        # Revenue estimate (Boxleiter method - conservative)
        revenue_estimate_cents = 0
        for g in games:
            owners_str = g.get("owners", "0 .. 0")
            min_owners, max_owners = self._parse_owners(owners_str)
            owners_mid = (min_owners + max_owners) // 2
            price = g.get("price", "0")
            if isinstance(price, str):
                price = int(price) if price.isdigit() else 0
            # Conservative: assume 50% bought at full price, 50% at discount
            estimated_revenue = int(owners_mid * price * 0.5)
            revenue_estimate_cents += estimated_revenue

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
                "price": g.get("price", 0),
            }
            for g in top_games
        ]

        # Upsert genre snapshot with enhanced data
        snapshot_data = {
            "genre": genre,
            "snapshot_date": today,
            # Core metrics
            "game_count": game_count,
            "total_ccu": total_ccu,
            "avg_ccu": avg_ccu,
            "total_owners_estimate": total_owners,
            "avg_review_score": avg_review_score,
            "top_games": top_games_data,
            # Enhanced metrics
            "avg_price_cents": avg_price_cents,
            "median_price_cents": median_price_cents,
            "price_distribution": price_distribution,
            "releases_last_30d": releases_last_30d,
            "releases_last_90d": releases_last_90d,
            "early_access_count": early_access_count,
            "early_access_pct": early_access_pct,
            "median_review_count": median_review_count,
            "avg_game_age_days": 0,  # Would need Steam Store API for accurate data
            "top_tags": top_tags,
            "revenue_estimate_cents": revenue_estimate_cents,
        }

        stmt = insert(GenreSnapshot).values(**snapshot_data)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_genre_snapshot_date",
            set_={k: stmt.excluded[k] for k in snapshot_data.keys() if k not in ["genre", "snapshot_date"]}
        )
        await self.db.execute(stmt)

        # Store individual game data (sample - top 100 to avoid huge tables)
        for g in sorted(games, key=lambda x: x.get("ccu", 0), reverse=True)[:100]:
            owners_str = g.get("owners", "0 .. 0")
            min_owners, max_owners = self._parse_owners(owners_str)
            pos = g.get("positive", 0)
            neg = g.get("negative", 0)
            total = pos + neg
            review_score = round((pos / total) * 100) if total > 0 else 0
            price = g.get("price", "0")
            if isinstance(price, str):
                price = int(price) if price.isdigit() else 0

            game_data = {
                "genre": genre,
                "snapshot_date": today,
                "app_id": int(g.get("appid", 0)),
                "name": g.get("name", "Unknown"),
                "ccu": g.get("ccu", 0),
                "owners_min": min_owners,
                "owners_max": max_owners,
                "reviews_positive": pos,
                "reviews_negative": neg,
                "review_score": review_score,
                "price_cents": price,
                "discount_percent": g.get("discount", 0),
                "is_early_access": "Early Access" in str(g.get("tags", {})),
                "tags": list(g.get("tags", {}).keys()) if isinstance(g.get("tags"), dict) else [],
            }

            stmt = insert(GenreGame).values(**game_data)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_genre_game_date",
                set_={k: stmt.excluded[k] for k in game_data.keys() if k not in ["genre", "app_id", "snapshot_date"]}
            )
            await self.db.execute(stmt)

        await self.db.commit()

    async def _calculate_genre_scores_enhanced(self):
        """Calculate enhanced hotness/fitness scores with velocity."""
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Get today's snapshots
        result = await self.db.execute(
            select(GenreSnapshot).where(GenreSnapshot.snapshot_date == today)
        )
        current_snapshots = {s.genre: s for s in result.scalars().all()}

        # Get week-ago snapshots for velocity calculation
        result = await self.db.execute(
            select(GenreSnapshot).where(
                GenreSnapshot.snapshot_date >= week_ago - timedelta(days=1),
                GenreSnapshot.snapshot_date <= week_ago
            )
        )
        previous_snapshots = {s.genre: s for s in result.scalars().all()}

        if not current_snapshots:
            return

        # Calculate relative scores
        max_ccu = max(s.total_ccu or 0 for s in current_snapshots.values())
        max_games = max(s.game_count or 0 for s in current_snapshots.values())
        max_revenue = max(s.revenue_estimate_cents or 0 for s in current_snapshots.values())

        for genre, snapshot in current_snapshots.items():
            # Core scores
            hotness = min(100, int((snapshot.total_ccu or 0) / max(max_ccu, 1) * 100)) if max_ccu > 0 else 50
            saturation = min(100, int((snapshot.game_count or 0) / max(max_games, 1) * 100)) if max_games > 0 else 50
            success_rate = snapshot.avg_review_score or 50
            timing = 100 - saturation

            # Enhanced: Growth velocity
            previous = previous_snapshots.get(genre)
            if previous and previous.total_ccu and previous.total_ccu > 0:
                growth_velocity = int(((snapshot.total_ccu - previous.total_ccu) / previous.total_ccu) * 100)
            else:
                growth_velocity = 0

            # Enhanced: Competition score (based on saturation + recent releases)
            competition_score = min(100, saturation + (snapshot.releases_last_30d or 0))

            # Enhanced: Revenue potential
            if max_revenue > 0:
                revenue_potential = min(100, int((snapshot.revenue_estimate_cents or 0) / max_revenue * 100))
            else:
                revenue_potential = 50

            # Enhanced: Discoverability (inverse of median reviews - fewer reviews = harder to discover)
            median_reviews = snapshot.median_review_count or 100
            if median_reviews < 50:
                discoverability = 30  # Hard to get noticed
            elif median_reviews < 200:
                discoverability = 50
            elif median_reviews < 1000:
                discoverability = 70
            else:
                discoverability = 90  # Lots of reviews = high engagement genre

            # Enhanced: Trend direction
            if growth_velocity >= 10:
                trend_direction = "rising"
            elif growth_velocity <= -10:
                trend_direction = "declining"
            else:
                trend_direction = "stable"

            # Overall score: weighted average with velocity bonus
            overall = int(
                (hotness * 0.30) +
                (success_rate * 0.25) +
                (timing * 0.20) +
                (revenue_potential * 0.15) +
                (min(100, max(0, growth_velocity + 50)) * 0.10)  # Velocity normalized to 0-100
            )

            # Recommendation
            if growth_velocity >= 15 and saturation < 50:
                recommendation = "hot"
            elif growth_velocity >= 5 or (overall >= 65 and saturation < 60):
                recommendation = "growing"
            elif growth_velocity <= -10:
                recommendation = "declining"
            elif saturation >= 70:
                recommendation = "saturated"
            else:
                recommendation = "niche"

            score_data = {
                "genre": genre,
                "score_date": today,
                # Core scores
                "hotness_score": hotness,
                "saturation_score": saturation,
                "success_rate_score": success_rate,
                "timing_score": timing,
                "overall_score": overall,
                "recommendation": recommendation,
                # Enhanced scores
                "growth_velocity": growth_velocity,
                "competition_score": competition_score,
                "revenue_potential_score": revenue_potential,
                "discoverability_score": discoverability,
                "trend_direction": trend_direction,
            }

            stmt = insert(GenreScore).values(**score_data)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_genre_score_date",
                set_={k: stmt.excluded[k] for k in score_data.keys() if k not in ["genre", "score_date"]}
            )
            await self.db.execute(stmt)

        await self.db.commit()
        logger.info(f"Calculated enhanced scores for {len(current_snapshots)} genres")

    def _calculate_price_distribution(self, prices: list) -> dict:
        """Bucket prices into ranges."""
        distribution = {
            "free": 0,
            "under_5": 0,
            "5_to_10": 0,
            "10_to_20": 0,
            "20_to_30": 0,
            "over_30": 0
        }
        for price in prices:
            if price == 0:
                distribution["free"] += 1
            elif price < 500:
                distribution["under_5"] += 1
            elif price < 1000:
                distribution["5_to_10"] += 1
            elif price < 2000:
                distribution["10_to_20"] += 1
            elif price < 3000:
                distribution["20_to_30"] += 1
            else:
                distribution["over_30"] += 1
        return distribution

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
