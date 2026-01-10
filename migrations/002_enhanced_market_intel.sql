-- Steam Intel Enhancement: Richer Market Intelligence Data
-- Migration: 002_enhanced_market_intel.sql
-- Created: 2025-01-10

-- ============================================
-- 1. Enhance genre_snapshots with pricing & release data
-- ============================================

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

-- ============================================
-- 2. Enhance genre_scores with velocity & trend data
-- ============================================

ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS growth_velocity INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS competition_score INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS revenue_potential_score INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS discoverability_score INTEGER;
ALTER TABLE genre_scores ADD COLUMN IF NOT EXISTS trend_direction VARCHAR(20);

-- ============================================
-- 3. Create genre_games table (full game list per genre)
-- ============================================

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
CREATE INDEX IF NOT EXISTS idx_genre_games_release ON genre_games(release_date DESC);

-- ============================================
-- 4. Create tag_correlations table (tag co-occurrence analysis)
-- ============================================

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
CREATE INDEX IF NOT EXISTS idx_tag_correlations_strength ON tag_correlations(correlation_strength DESC);

-- ============================================
-- 5. Create market_trends table (weekly aggregates)
-- ============================================

CREATE TABLE IF NOT EXISTS market_trends (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    week_start DATE NOT NULL,
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
    trend_score INTEGER,
    trend_label VARCHAR(20),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_market_trend_week UNIQUE (week_start, genre)
);

CREATE INDEX IF NOT EXISTS idx_market_trends_genre ON market_trends(genre, week_start DESC);

-- ============================================
-- 6. Create upcoming_releases table (competitive intel)
-- ============================================

CREATE TABLE IF NOT EXISTS upcoming_releases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    app_id INTEGER NOT NULL,
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
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_upcoming_app UNIQUE (app_id)
);

CREATE INDEX IF NOT EXISTS idx_upcoming_releases_date ON upcoming_releases(expected_release);
CREATE INDEX IF NOT EXISTS idx_upcoming_genres ON upcoming_releases USING GIN(genres);

-- ============================================
-- Done!
-- ============================================
