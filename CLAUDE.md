# CLAUDE.md - Steam Intel Service

This file provides guidance to Claude Code when working with this repository.

## Service Identity

**Service Name:** Steam Intel
**Role:** Steam API data collection, portfolio analytics, market intelligence
**Port:** 8080
**Production URL:** https://api.alorfutures.com/steam
**API Docs:** http://91.99.63.4:8080/docs

## ALOR Services Ecosystem

This service is part of the ALOR Enterprises microservices architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ALOR Services Ecosystem                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │    FBL      │◄───│ Steam Intel │    │  Email Ops  │          │
│  │  (Frontend) │    │   (Data)    │    │    (AI)     │          │
│  │             │    │             │    │             │          │
│  │ React/Vite  │    │  FastAPI    │    │  FastAPI    │          │
│  │ Supabase    │    │  Port 8080  │    │  Port 8081  │          │
│  │ Netlify     │    │  Hetzner    │    │  Hetzner    │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Service Responsibilities

| Service | Repository | Purpose |
|---------|------------|---------|
| **FBL** | fbl-fasttrack | Publisher operations frontend + Supabase backend |
| **Steam Intel** | steam-intel | This repo - Steam API data, analytics |
| **Email Ops** | email-coo | AI email classification, auto-response |

## What Steam Intel Does

1. **Collects portfolio game data** via SteamSpy API
2. **Tracks market trends** (top sellers, new releases, genre heatmaps)
3. **Monitors revenue** from Steam Partner API (with whitelisted IP)
4. **Provides analytics** to FBL frontend via REST API

## API Endpoints

### Portfolio (FBL Integration)
```
GET  /api/v1/portfolio                    # All 9 published games with stats
GET  /api/v1/portfolio/{app_id}           # Single game details
GET  /api/v1/portfolio/{app_id}/history   # Historical data (30d, 90d)
GET  /api/v1/portfolio/{app_id}/wow       # Week-over-week changes
```

### Revenue
```
GET  /api/v1/revenue/summary?period=30d   # Portfolio revenue summary
GET  /api/v1/revenue/{app_id}?period=90d  # Game revenue with daily trend
```

### Market Intelligence
```
GET  /api/v1/market/heatmap/enhanced      # Genre heatmap with velocity
GET  /api/v1/market/trending              # Trending games
GET  /api/v1/market/tag-combos            # Tag correlations
```

### Admin (Manual Triggers)
```
POST /api/v1/admin/collect/portfolio      # Trigger portfolio collection
POST /api/v1/admin/collect/market         # Trigger market data collection
POST /api/v1/admin/collect/genres         # Trigger genre trends collection
```

## Technology Stack

- **Framework:** FastAPI (async Python)
- **Database:** PostgreSQL (Hetzner)
- **Data Sources:** SteamSpy API, Steam Store API, Steam Partner API
- **Scheduler:** APScheduler (runs every 6 hours)
- **Deployment:** Docker on Hetzner VPS

## Configuration

### Environment Variables

```bash
STEAM_API_KEY=...                  # Steam Web API key
STEAM_PARTNER_KEY=...              # Steam Partner API key (IP whitelisted)
DATABASE_URL=postgresql+asyncpg://...
API_SECRET_KEY=...                 # For X-API-Key header
PUBLISHER_GAMES=1129260,1560160,2074740,2368300,2602030,2412200,446760,346180,548230
```

### Published Games (Portfolio)

| App ID | Game |
|--------|------|
| 1129260 | Game 1 |
| 1560160 | Game 2 |
| 2074740 | Game 3 |
| 2368300 | Game 4 |
| 2602030 | Game 5 |
| 2412200 | Game 6 |
| 446760 | Game 7 |
| 346180 | Game 8 |
| 548230 | Game 9 |

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI application entry |
| `app/api/portfolio.py` | Portfolio endpoints (FBL uses these) |
| `app/api/market.py` | Market intelligence endpoints |
| `app/api/revenue.py` | Revenue tracking endpoints |
| `app/collectors/steamspy.py` | SteamSpy data collector |
| `app/scheduler.py` | Background job scheduler |

## Database Models

- `games` - Game metadata (app_id, name, is_portfolio)
- `game_snapshots` - Point-in-time stats (CCU, reviews, owners)
- `top_sellers_snapshots` - Market ranking snapshots
- `genre_trends` - Genre performance over time

## FBL Integration

FBL's Portfolio view calls Steam Intel:

```typescript
// FBL: src/components/admin/views/AnalyticsView.tsx
const response = await fetch('https://api.alorfutures.com/steam/api/v1/portfolio', {
  headers: { 'X-API-Key': 'your-api-key' }
})
```

Response format:
```json
{
  "total_games": 9,
  "total_ccu": 1234,
  "total_reviews": 50000,
  "avg_review_score": 85.5,
  "games": [
    {
      "app_id": 1129260,
      "name": "Game Name",
      "ccu": 100,
      "reviews_positive": 1000,
      "reviews_negative": 50,
      "review_score": 95,
      "owners_min": 100000,
      "owners_max": 200000,
      "avg_playtime_hours": 15.5,
      "snapshot_date": "2024-01-15"
    }
  ]
}
```

## Deployment

### Server
- **Host:** 91.99.63.4 (Hetzner VPS)
- **Port:** 8080
- **Database:** steam_intel (PostgreSQL)

### Deploy Command
```bash
ssh root@91.99.63.4
cd /opt/alor-services/steam-intel
git pull && docker-compose -f docker-compose.prod.yml up -d --build
```

## Scheduler

Automatic data collection runs every 6 hours:
- Portfolio stats (SteamSpy)
- Market data (top sellers, new releases)
- Genre trends

Manual trigger available via admin endpoints.

## For Other Developers

To adapt this service for another business:

1. **Fork the repository**
2. **Configure PUBLISHER_GAMES** with your Steam App IDs
3. **Set up Steam API keys**
4. **Deploy to your server**
5. **Call endpoints from your frontend**

The service is designed to be reusable for any Steam-based analytics needs.
