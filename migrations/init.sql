-- Steam Intelligence Service - Database Schema
-- Run this to initialize the database

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- GAMES & SNAPSHOTS
-- ============================================================================

-- Games we're tracking (FBL portfolio + any others)
CREATE TABLE games (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    app_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    developer VARCHAR(255),
    publisher VARCHAR(255),
    release_date DATE,
    price_cents INTEGER,
    genres TEXT[],
    tags TEXT[],
    is_portfolio BOOLEAN DEFAULT false,  -- Is this an FBL game?
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Point-in-time snapshots of game stats
CREATE TABLE game_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    app_id INTEGER NOT NULL,  -- Denormalized for fast queries

    -- Ownership & Players
    owners_min INTEGER,
    owners_max INTEGER,
    ccu INTEGER,  -- Concurrent users
    players_2weeks INTEGER,

    -- Playtime
    avg_playtime_minutes INTEGER,
    median_playtime_minutes INTEGER,
    avg_playtime_2weeks_minutes INTEGER,

    -- Reviews
    reviews_positive INTEGER,
    reviews_negative INTEGER,
    review_score INTEGER,  -- Percentage positive

    -- Pricing
    price_cents INTEGER,
    discount_percent INTEGER,

    -- Metadata
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique snapshot per game per day
    UNIQUE(app_id, snapshot_date)
);

-- Index for time-series queries
CREATE INDEX idx_game_snapshots_app_date ON game_snapshots(app_id, snapshot_date DESC);
CREATE INDEX idx_game_snapshots_date ON game_snapshots(snapshot_date DESC);

-- ============================================================================
-- MARKET INTELLIGENCE
-- ============================================================================

-- Genre/tag trend snapshots
CREATE TABLE genre_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    genre VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL,

    -- Metrics
    game_count INTEGER,
    total_ccu INTEGER,
    avg_ccu INTEGER,
    total_owners_estimate INTEGER,
    avg_review_score INTEGER,

    -- Top games in this genre at snapshot time
    top_games JSONB,  -- [{app_id, name, ccu, owners}]

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(genre, snapshot_date)
);

CREATE INDEX idx_genre_snapshots_genre_date ON genre_snapshots(genre, snapshot_date DESC);

-- Top sellers snapshots
CREATE TABLE top_sellers_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_date DATE NOT NULL,
    category VARCHAR(50) NOT NULL,  -- 'global', 'indie', 'action', etc.

    -- Top 100 at snapshot time
    rankings JSONB NOT NULL,  -- [{rank, app_id, name, price}]

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(category, snapshot_date)
);

-- New releases tracking
CREATE TABLE new_releases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    app_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    release_date DATE NOT NULL,
    genres TEXT[],
    tags TEXT[],
    price_cents INTEGER,

    -- First week performance
    week1_ccu INTEGER,
    week1_reviews INTEGER,
    week1_review_score INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(app_id)
);

-- ============================================================================
-- REVENUE (Partner API - requires IP whitelist)
-- ============================================================================

CREATE TABLE revenue_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    app_id INTEGER NOT NULL,

    -- Period
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    period_type VARCHAR(20) NOT NULL,  -- 'daily', 'weekly', 'monthly'

    -- Revenue
    gross_revenue_cents BIGINT,
    net_revenue_cents BIGINT,
    units_sold INTEGER,
    refunds INTEGER,

    -- By region (optional breakdown)
    region_breakdown JSONB,  -- {US: {revenue, units}, EU: {...}}

    -- Source
    source VARCHAR(50) DEFAULT 'partner_api',
    raw_data JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(app_id, period_start, period_end, period_type)
);

CREATE INDEX idx_revenue_app_period ON revenue_records(app_id, period_start DESC);

-- ============================================================================
-- ANALYTICS & COMPUTED
-- ============================================================================

-- Pre-computed comparisons (FBL vs market)
CREATE TABLE portfolio_benchmarks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    benchmark_date DATE NOT NULL,

    -- Portfolio aggregates
    portfolio_total_ccu INTEGER,
    portfolio_avg_review_score INTEGER,
    portfolio_total_owners_estimate INTEGER,

    -- Market averages (indie games)
    market_avg_ccu INTEGER,
    market_avg_review_score INTEGER,
    market_median_owners INTEGER,

    -- Computed
    ccu_vs_market_pct INTEGER,  -- +/- percentage
    reviews_vs_market_pct INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(benchmark_date)
);

-- Game scoring for submissions (genre fit, market timing)
CREATE TABLE genre_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    genre VARCHAR(100) NOT NULL,
    score_date DATE NOT NULL,

    -- Scores (0-100)
    hotness_score INTEGER,  -- Based on CCU growth
    saturation_score INTEGER,  -- How crowded
    success_rate_score INTEGER,  -- % of games with good reviews
    timing_score INTEGER,  -- Good time to release?

    -- Overall recommendation
    overall_score INTEGER,
    recommendation TEXT,  -- 'hot', 'growing', 'saturated', 'declining'

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(genre, score_date)
);

-- ============================================================================
-- SYSTEM
-- ============================================================================

-- Collection job tracking
CREATE TABLE collection_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collector_name VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'completed', 'failed'
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_collection_runs_name_date ON collection_runs(collector_name, started_at DESC);

-- API request logging
CREATE TABLE api_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    client_ip VARCHAR(45),
    response_status INTEGER,
    response_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Partition api_logs by month for performance (optional)
CREATE INDEX idx_api_logs_created ON api_logs(created_at DESC);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Latest stats for portfolio games
CREATE VIEW v_portfolio_latest AS
SELECT
    g.app_id,
    g.name,
    g.developer,
    g.release_date,
    gs.ccu,
    gs.owners_min,
    gs.owners_max,
    gs.reviews_positive,
    gs.reviews_negative,
    gs.review_score,
    gs.avg_playtime_minutes / 60.0 as avg_playtime_hours,
    gs.price_cents / 100.0 as price,
    gs.snapshot_date
FROM games g
JOIN LATERAL (
    SELECT * FROM game_snapshots
    WHERE app_id = g.app_id
    ORDER BY snapshot_date DESC
    LIMIT 1
) gs ON true
WHERE g.is_portfolio = true
ORDER BY gs.ccu DESC;

-- Week-over-week changes
CREATE VIEW v_portfolio_wow AS
SELECT
    g.app_id,
    g.name,
    current.ccu as current_ccu,
    previous.ccu as previous_ccu,
    CASE WHEN previous.ccu > 0
        THEN ROUND(((current.ccu - previous.ccu)::numeric / previous.ccu) * 100, 1)
        ELSE NULL
    END as ccu_change_pct,
    current.reviews_positive - COALESCE(previous.reviews_positive, 0) as new_reviews,
    current.snapshot_date
FROM games g
JOIN LATERAL (
    SELECT * FROM game_snapshots
    WHERE app_id = g.app_id
    ORDER BY snapshot_date DESC
    LIMIT 1
) current ON true
LEFT JOIN LATERAL (
    SELECT * FROM game_snapshots
    WHERE app_id = g.app_id
    AND snapshot_date <= current.snapshot_date - INTERVAL '7 days'
    ORDER BY snapshot_date DESC
    LIMIT 1
) previous ON true
WHERE g.is_portfolio = true;
