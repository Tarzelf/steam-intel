# Steam Intel Enhancement Spec
> More data, better insights for FBL Market Intel

## Overview

Current system collects basic genre aggregates (CCU, game count, review scores). This spec adds richer market intelligence data for better decision-making.

---

## 1. Enhanced Genre Snapshots

### New Columns for `genre_snapshots` table

```sql
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS avg_price_cents INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS median_price_cents INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS price_distribution JSONB;  -- {under_5: 120, 5_to_10: 340, 10_to_20: 200, 20_to_30: 80, over_30: 40}
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS releases_last_30d INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS releases_last_90d INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS early_access_count INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS early_access_pct INTEGER;  -- Percentage of games in EA
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS median_review_count INTEGER;  -- Visibility indicator
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS avg_game_age_days INTEGER;  -- How old are games in this genre
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS top_tags JSONB;  -- [{tag: "Roguelike", count: 450}, ...] - common co-occurring tags
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS revenue_estimate_cents BIGINT;  -- Gross revenue estimate for genre
```

### New Columns for `genre_scores` table

```sql
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS growth_velocity INTEGER;  -- Week-over-week CCU change %
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS competition_score INTEGER;  -- 0-100, based on releases + saturation
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS revenue_potential_score INTEGER;  -- Based on avg price * success rate
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS discoverability_score INTEGER;  -- Based on median review count (lower = harder)
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS trend_direction VARCHAR(20);  -- 'rising', 'stable', 'declining'
```

---

## 2. New Table: `genre_games` (Detailed Game List Per Genre)

Instead of just top 10, store ALL games per genre for deeper analysis.

```sql
CREATE TABLE IF NOT EXISTS genre_games (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    genre VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL,
    app_id INTEGER NOT NULL,
    name VARCHAR(255),
    ccu INTEGER,
    owners_min INTEGER,
    owners_max INTEGER,
    reviews_positive INTEGER,
    reviews_negative INTEGER,
    review_score INTEGER,
    price_cents INTEGER,
    discount_percent INTEGER,
    release_date DATE,
    is_early_access BOOLEAN DEFAULT FALSE,
    tags JSONB,  -- All tags for this game
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_genre_game_date UNIQUE (genre, app_id, snapshot_date)
);

CREATE INDEX idx_genre_games_genre_date ON genre_games(genre, snapshot_date DESC);
CREATE INDEX idx_genre_games_ccu ON genre_games(ccu DESC);
CREATE INDEX idx_genre_games_release ON genre_games(release_date DESC);
```

---

## 3. New Table: `tag_correlations` (Tag Co-occurrence Analysis)

```sql
CREATE TABLE IF NOT EXISTS tag_correlations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tag_a VARCHAR(100) NOT NULL,
    tag_b VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL,
    co_occurrence_count INTEGER,  -- Games with both tags
    correlation_strength FLOAT,  -- 0.0 to 1.0
    combined_ccu INTEGER,  -- Total CCU of games with both tags
    avg_review_score INTEGER,
    avg_price_cents INTEGER,
    top_games JSONB,  -- Top 5 games with both tags
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_tag_correlation_date UNIQUE (tag_a, tag_b, snapshot_date)
);

CREATE INDEX idx_tag_correlations_date ON tag_correlations(snapshot_date DESC);
CREATE INDEX idx_tag_correlations_strength ON tag_correlations(correlation_strength DESC);
```

---

## 4. New Table: `market_trends` (Weekly Aggregates for Trend Analysis)

```sql
CREATE TABLE IF NOT EXISTS market_trends (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    week_start DATE NOT NULL,  -- Monday of the week
    genre VARCHAR(100) NOT NULL,

    -- Weekly metrics
    total_ccu INTEGER,
    game_count INTEGER,
    new_releases INTEGER,
    avg_review_score INTEGER,
    avg_price_cents INTEGER,

    -- Week-over-week changes
    ccu_change_pct FLOAT,
    game_count_change_pct FLOAT,

    -- Computed trend
    trend_score INTEGER,  -- -100 to +100
    trend_label VARCHAR(20),  -- 'surging', 'growing', 'stable', 'declining', 'crashing'

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_market_trend_week UNIQUE (week_start, genre)
);

CREATE INDEX idx_market_trends_genre ON market_trends(genre, week_start DESC);
```

---

## 5. New Table: `upcoming_releases` (Competitive Intelligence)

```sql
CREATE TABLE IF NOT EXISTS upcoming_releases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    app_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    developer VARCHAR(255),
    publisher VARCHAR(255),
    expected_release DATE,  -- From Steam "Coming Soon"
    genres TEXT[],
    tags TEXT[],
    price_cents INTEGER,  -- Expected price if announced
    has_demo BOOLEAN DEFAULT FALSE,
    wishlist_estimate INTEGER,  -- Estimated from follower signals
    hype_score INTEGER,  -- 0-100 based on community buzz
    source VARCHAR(50),  -- 'steam', 'itch', 'press'
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_upcoming_app UNIQUE (app_id)
);

CREATE INDEX idx_upcoming_releases_date ON upcoming_releases(expected_release);
CREATE INDEX idx_upcoming_genres ON upcoming_releases USING GIN(genres);
```

---

## 6. Enhanced GenreCollector

Update `app/collectors/genres.py` to collect additional data:

```python
async def _collect_genre_enhanced(self, genre: str) -> dict:
    """Collect enhanced genre data including pricing and release analysis."""

    # Fetch all games for genre (not just top)
    games = await self._fetch_all_genre_games(genre)

    # Calculate enhanced metrics
    prices = [g['price'] for g in games if g.get('price')]
    release_dates = [g['release_date'] for g in games if g.get('release_date')]

    metrics = {
        # Existing metrics
        'game_count': len(games),
        'total_ccu': sum(g.get('ccu', 0) for g in games),
        'avg_ccu': ...,
        'avg_review_score': ...,

        # NEW: Pricing metrics
        'avg_price_cents': int(statistics.mean(prices)) if prices else 0,
        'median_price_cents': int(statistics.median(prices)) if prices else 0,
        'price_distribution': self._calculate_price_distribution(prices),

        # NEW: Release metrics
        'releases_last_30d': self._count_recent_releases(release_dates, 30),
        'releases_last_90d': self._count_recent_releases(release_dates, 90),

        # NEW: Early Access
        'early_access_count': sum(1 for g in games if g.get('is_early_access')),
        'early_access_pct': ...,

        # NEW: Visibility
        'median_review_count': self._calculate_median_reviews(games),

        # NEW: Age analysis
        'avg_game_age_days': self._calculate_avg_age(release_dates),

        # NEW: Tag co-occurrence
        'top_tags': self._extract_top_cooccurring_tags(games, genre),

        # NEW: Revenue estimate
        'revenue_estimate_cents': self._estimate_genre_revenue(games),
    }

    return metrics

def _calculate_price_distribution(self, prices: list) -> dict:
    """Bucket prices into ranges."""
    distribution = {
        'free': 0,
        'under_5': 0,
        '5_to_10': 0,
        '10_to_20': 0,
        '20_to_30': 0,
        'over_30': 0
    }
    for price in prices:
        if price == 0:
            distribution['free'] += 1
        elif price < 500:
            distribution['under_5'] += 1
        elif price < 1000:
            distribution['5_to_10'] += 1
        elif price < 2000:
            distribution['10_to_20'] += 1
        elif price < 3000:
            distribution['20_to_30'] += 1
        else:
            distribution['over_30'] += 1
    return distribution

def _estimate_genre_revenue(self, games: list) -> int:
    """Estimate gross revenue using Boxleiter method."""
    total = 0
    for game in games:
        owners_mid = (game.get('owners_min', 0) + game.get('owners_max', 0)) // 2
        price = game.get('price', 0)
        # Boxleiter: ~30% buy at full price, rest at discount
        estimated_revenue = int(owners_mid * price * 0.5)  # Conservative
        total += estimated_revenue
    return total
```

---

## 7. New Collector: `TagCorrelationCollector`

```python
# app/collectors/correlations.py

class TagCorrelationCollector(BaseCollector):
    """Analyzes tag co-occurrence patterns."""

    INTERESTING_TAG_PAIRS = [
        ('Roguelike', 'Deck Building'),
        ('Roguelike', 'Action'),
        ('Souls-like', 'Action'),
        ('Metroidvania', 'Pixel Graphics'),
        ('Survival', 'Crafting'),
        ('Horror', 'Survival'),
        ('Co-op', 'Action'),
        ('Strategy', 'Turn-Based'),
        # ... more pairs
    ]

    async def collect(self):
        """Collect tag correlation data."""
        for tag_a, tag_b in self.INTERESTING_TAG_PAIRS:
            await self._analyze_tag_pair(tag_a, tag_b)
            await asyncio.sleep(self.rate_limit_delay)

    async def _analyze_tag_pair(self, tag_a: str, tag_b: str):
        """Analyze co-occurrence of two tags."""
        # Fetch games with tag_a
        games_a = await self._fetch_games_with_tag(tag_a)
        games_b = await self._fetch_games_with_tag(tag_b)

        # Find intersection
        app_ids_a = {g['app_id'] for g in games_a}
        app_ids_b = {g['app_id'] for g in games_b}
        common_ids = app_ids_a & app_ids_b

        if not common_ids:
            return

        # Analyze common games
        common_games = [g for g in games_a if g['app_id'] in common_ids]

        correlation = TagCorrelation(
            tag_a=tag_a,
            tag_b=tag_b,
            snapshot_date=date.today(),
            co_occurrence_count=len(common_ids),
            correlation_strength=len(common_ids) / min(len(app_ids_a), len(app_ids_b)),
            combined_ccu=sum(g.get('ccu', 0) for g in common_games),
            avg_review_score=statistics.mean(g.get('review_score', 0) for g in common_games),
            avg_price_cents=statistics.mean(g.get('price', 0) for g in common_games),
            top_games=sorted(common_games, key=lambda x: x.get('ccu', 0), reverse=True)[:5]
        )

        await self._upsert_correlation(correlation)
```

---

## 8. New Collector: `UpcomingReleasesCollector`

```python
# app/collectors/upcoming.py

class UpcomingReleasesCollector(BaseCollector):
    """Tracks upcoming releases for competitive intelligence."""

    async def collect(self):
        """Collect upcoming releases from Steam Coming Soon."""
        # Fetch coming soon from Steam Store API
        url = "https://store.steampowered.com/api/featuredcategories/"
        data = await self._fetch_json(url)

        coming_soon = data.get('coming_soon', {}).get('items', [])

        for item in coming_soon:
            app_id = item.get('id')

            # Get detailed app info
            details = await self._get_app_details(app_id)
            if not details:
                continue

            release = UpcomingRelease(
                app_id=app_id,
                name=details.get('name'),
                developer=details.get('developers', [None])[0],
                publisher=details.get('publishers', [None])[0],
                expected_release=self._parse_release_date(details.get('release_date', {})),
                genres=[g['description'] for g in details.get('genres', [])],
                tags=self._extract_tags(details),
                price_cents=details.get('price_overview', {}).get('initial', 0),
                has_demo=details.get('demos') is not None,
            )

            await self._upsert_release(release)
            await asyncio.sleep(0.5)  # Rate limit
```

---

## 9. New API Endpoints

### Enhanced Heatmap

```python
# GET /api/v1/market/heatmap/enhanced
@router.get("/heatmap/enhanced")
async def get_enhanced_heatmap():
    """Returns heatmap with all new metrics."""
    return {
        "genres": [
            {
                "genre": "Roguelike",
                "hotness": 85,
                "saturation": 45,
                "success_rate": 72,
                "timing": 55,
                "overall": 78,
                "recommendation": "hot",

                # NEW FIELDS
                "growth_velocity": 12,  # +12% week-over-week
                "trend_direction": "rising",
                "competition_score": 62,
                "revenue_potential": 78,
                "discoverability": 45,

                # Pricing insights
                "avg_price_cents": 1499,
                "median_price_cents": 1299,
                "price_distribution": {
                    "free": 5,
                    "under_5": 120,
                    "5_to_10": 340,
                    "10_to_20": 200,
                    "20_to_30": 80,
                    "over_30": 40
                },

                # Release activity
                "releases_last_30d": 45,
                "releases_last_90d": 180,
                "early_access_pct": 32,

                # Market size
                "total_ccu": 125000,
                "game_count": 1200,
                "revenue_estimate_millions": 45.2,

                # Competition
                "upcoming_releases_count": 23,
                "top_upcoming": [
                    {"name": "Game X", "expected_release": "2025-03"}
                ],

                # Tag combos
                "hot_tag_combos": [
                    {"tags": ["Roguelike", "Deck Building"], "score": 92},
                    {"tags": ["Roguelike", "Action"], "score": 78}
                ],

                "top_games": [...]
            }
        ],
        "snapshot_date": "2025-01-10"
    }
```

### Tag Correlations Endpoint

```python
# GET /api/v1/market/tag-combos
@router.get("/tag-combos")
async def get_tag_combinations():
    """Returns profitable tag combinations."""
    return {
        "combinations": [
            {
                "tags": ["Roguelike", "Deck Building"],
                "game_count": 89,
                "total_ccu": 45000,
                "avg_review_score": 82,
                "avg_price_cents": 1599,
                "correlation_strength": 0.72,
                "top_games": [...]
            }
        ]
    }
```

### Upcoming Releases Endpoint

```python
# GET /api/v1/market/upcoming?genre=Roguelike
@router.get("/upcoming")
async def get_upcoming_releases(genre: str = None):
    """Returns upcoming releases, optionally filtered by genre."""
    return {
        "releases": [
            {
                "app_id": 123456,
                "name": "Upcoming Game",
                "developer": "Indie Dev",
                "expected_release": "2025-03-15",
                "genres": ["Roguelike", "Action"],
                "has_demo": True,
                "wishlist_estimate": 50000,
                "hype_score": 72
            }
        ],
        "total_count": 23
    }
```

### Market Trends Endpoint

```python
# GET /api/v1/market/trends?genre=Roguelike&weeks=12
@router.get("/trends")
async def get_market_trends(genre: str, weeks: int = 12):
    """Returns weekly trend data for a genre."""
    return {
        "genre": "Roguelike",
        "weeks": [
            {
                "week_start": "2025-01-06",
                "total_ccu": 125000,
                "game_count": 1200,
                "new_releases": 12,
                "ccu_change_pct": 5.2,
                "trend_label": "growing"
            }
        ],
        "overall_trend": "rising",
        "forecast": "continued_growth"
    }
```

---

## 10. Scheduler Updates

```python
# app/scheduler.py

def setup_scheduler():
    scheduler = AsyncIOScheduler()

    # Existing jobs
    scheduler.add_job(portfolio_collector.collect, 'interval', hours=6)
    scheduler.add_job(market_collector.collect, 'interval', hours=24)
    scheduler.add_job(genre_collector.collect, 'interval', hours=24)

    # NEW: Enhanced genre collection (runs after basic genre collection)
    scheduler.add_job(genre_collector.collect_enhanced, 'interval', hours=24)

    # NEW: Tag correlation analysis (weekly)
    scheduler.add_job(correlation_collector.collect, 'interval', days=7)

    # NEW: Upcoming releases (daily)
    scheduler.add_job(upcoming_collector.collect, 'interval', hours=24)

    # NEW: Market trends aggregation (weekly on Sunday)
    scheduler.add_job(
        trend_aggregator.aggregate_weekly,
        'cron',
        day_of_week='sun',
        hour=3
    )

    scheduler.start()
```

---

## 11. Migration SQL

```sql
-- migrations/002_enhanced_market_intel.sql

-- 1. Enhance genre_snapshots
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS avg_price_cents INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS median_price_cents INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS price_distribution JSONB;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS releases_last_30d INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS releases_last_90d INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS early_access_count INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS early_access_pct INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS median_review_count INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS avg_game_age_days INTEGER;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS top_tags JSONB;
ALTER TABLE genre_snapshots ADD COLUMN IF NOT EXISTS revenue_estimate_cents BIGINT;

-- 2. Enhance genre_scores
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS growth_velocity INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS competition_score INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS revenue_potential_score INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS discoverability_score INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS trend_direction VARCHAR(20);

-- 3. Create genre_games table
CREATE TABLE IF NOT EXISTS genre_games (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    genre VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL,
    app_id INTEGER NOT NULL,
    name VARCHAR(255),
    ccu INTEGER,
    owners_min INTEGER,
    owners_max INTEGER,
    reviews_positive INTEGER,
    reviews_negative INTEGER,
    review_score INTEGER,
    price_cents INTEGER,
    discount_percent INTEGER,
    release_date DATE,
    is_early_access BOOLEAN DEFAULT FALSE,
    tags JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_genre_game_date UNIQUE (genre, app_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_genre_games_genre_date ON genre_games(genre, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_genre_games_ccu ON genre_games(ccu DESC);

-- 4. Create tag_correlations table
CREATE TABLE IF NOT EXISTS tag_correlations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tag_a VARCHAR(100) NOT NULL,
    tag_b VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL,
    co_occurrence_count INTEGER,
    correlation_strength FLOAT,
    combined_ccu INTEGER,
    avg_review_score INTEGER,
    avg_price_cents INTEGER,
    top_games JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_tag_correlation_date UNIQUE (tag_a, tag_b, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_tag_correlations_date ON tag_correlations(snapshot_date DESC);

-- 5. Create market_trends table
CREATE TABLE IF NOT EXISTS market_trends (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    week_start DATE NOT NULL,
    genre VARCHAR(100) NOT NULL,
    total_ccu INTEGER,
    game_count INTEGER,
    new_releases INTEGER,
    avg_review_score INTEGER,
    avg_price_cents INTEGER,
    ccu_change_pct FLOAT,
    game_count_change_pct FLOAT,
    trend_score INTEGER,
    trend_label VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_market_trend_week UNIQUE (week_start, genre)
);
CREATE INDEX IF NOT EXISTS idx_market_trends_genre ON market_trends(genre, week_start DESC);

-- 6. Create upcoming_releases table
CREATE TABLE IF NOT EXISTS upcoming_releases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    app_id INTEGER NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    developer VARCHAR(255),
    publisher VARCHAR(255),
    expected_release DATE,
    genres TEXT[],
    tags TEXT[],
    price_cents INTEGER,
    has_demo BOOLEAN DEFAULT FALSE,
    wishlist_estimate INTEGER,
    hype_score INTEGER,
    source VARCHAR(50),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_upcoming_releases_date ON upcoming_releases(expected_release);
CREATE INDEX IF NOT EXISTS idx_upcoming_genres ON upcoming_releases USING GIN(genres);
```

---

## 12. Summary for Developer

### New Files to Create:
1. `app/collectors/correlations.py` - TagCorrelationCollector
2. `app/collectors/upcoming.py` - UpcomingReleasesCollector
3. `app/collectors/trends.py` - TrendAggregator
4. `app/models/correlations.py` - TagCorrelation model
5. `app/models/upcoming.py` - UpcomingRelease model
6. `app/models/trends.py` - MarketTrend model
7. `migrations/002_enhanced_market_intel.sql` - Database migration

### Files to Modify:
1. `app/collectors/genres.py` - Add enhanced collection methods
2. `app/models/market.py` - Add new columns to GenreSnapshot, GenreScore
3. `app/api/market.py` - Add new endpoints
4. `app/scheduler.py` - Add new scheduled jobs
5. `app/main.py` - Register new routers

### New API Endpoints:
- `GET /api/v1/market/heatmap/enhanced` - Full enhanced heatmap
- `GET /api/v1/market/tag-combos` - Tag correlation data
- `GET /api/v1/market/upcoming` - Upcoming releases
- `GET /api/v1/market/trends` - Weekly trend data
- `POST /api/v1/admin/collect/correlations` - Manual trigger
- `POST /api/v1/admin/collect/upcoming` - Manual trigger

### Important Notes:
1. **Constraint Naming**: Always use explicit constraint names like `uq_genre_game_date` to avoid PostgreSQL auto-naming issues
2. **Rate Limiting**: SteamSpy needs 1.5s between requests; enhanced collection will take longer
3. **Data Volume**: `genre_games` table will be large (~50k+ rows per snapshot); consider retention policy
4. **Revenue Estimates**: Use Boxleiter method (conservative) for revenue calculations

---

## 13. Priority Order

**Phase 1 (High Impact, Quick Win):**
- Enhanced genre_snapshots columns (pricing, releases, EA%)
- Enhanced genre_scores (growth velocity, trend direction)
- Enhanced heatmap endpoint

**Phase 2 (Medium Effort):**
- Tag correlations table + collector
- Tag combos endpoint

**Phase 3 (Competitive Intel):**
- Upcoming releases table + collector
- Market trends aggregation

---

*Created: January 10, 2025*
