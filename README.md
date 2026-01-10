# Steam Intelligence Service

A containerized microservice that collects, stores, and serves Steam game analytics data. Designed to run on a VPS with a whitelisted IP for Steam Partner API access.

**Part of ALOR Enterprises services ecosystem** - follows [ALOR Services architecture patterns](../alor-services/ARCHITECTURE.md).

## Features

- **Game Stats Collection** - Daily snapshots of owners, CCU, reviews, playtime
- **Market Intelligence** - Genre trends, top sellers, new releases
- **Portfolio Tracking** - Monitor your published games over time
- **Financial Data** (Partner API) - Revenue, sales reports (requires IP whitelist)
- **Historical Analysis** - Week-over-week, month-over-month trends
- **REST API** - Secure endpoints for your apps to consume

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Hetzner VPS                          │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   PostgreSQL    │  │    Steam Intel Service      │  │
│  │   (Database)    │◄─┤                             │  │
│  │                 │  │  - Collectors (cron jobs)   │  │
│  │  - game_stats   │  │  - REST API (FastAPI)       │  │
│  │  - market_data  │  │  - Analysis Engine          │  │
│  │  - revenue      │  │                             │  │
│  └─────────────────┘  └──────────────┬──────────────┘  │
│                                      │                  │
│                              Port 8080 (API)            │
└──────────────────────────────────────┼──────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
               FBL Admin          Other Apps         Webhooks
```

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_ORG/steam-intel.git
cd steam-intel

# Copy env template
cp .env.example .env
# Edit .env with your Steam API key and database credentials

# Run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f
```

## Configuration

```env
# .env
STEAM_API_KEY=your_steam_api_key
DATABASE_URL=postgresql://user:pass@db:5432/steam_intel
API_SECRET_KEY=your_api_secret_for_clients
PUBLISHER_ID=FirstBreakLabs

# Optional: Partner API (requires IP whitelist)
STEAM_PARTNER_KEY=your_partner_key
```

## API Endpoints

All endpoints require `X-API-Key` header.

### Portfolio Stats
```
GET /api/v1/portfolio
GET /api/v1/portfolio/{app_id}
GET /api/v1/portfolio/{app_id}/history?period=30d
```

### Market Intelligence
```
GET /api/v1/market/genres
GET /api/v1/market/trending
GET /api/v1/market/top-sellers
```

### Game Analysis
```
POST /api/v1/analyze/game
  Body: { "app_id": 123456 }

POST /api/v1/analyze/comparable
  Body: { "tags": ["roguelike", "indie"], "price_range": [10, 20] }
```

### Revenue (Partner API)
```
GET /api/v1/revenue/summary
GET /api/v1/revenue/{app_id}
GET /api/v1/revenue/{app_id}/monthly
```

## Data Collection Schedule

| Collector | Frequency | Source |
|-----------|-----------|--------|
| Portfolio Stats | Every 6 hours | SteamSpy |
| Market Trends | Daily | Steam Store API |
| Genre Analysis | Weekly | SteamSpy |
| Revenue Sync | Daily | Steam Partner API |

## Database Schema

See `schema.sql` for full schema. Key tables:

- `games` - Game metadata
- `game_snapshots` - Point-in-time stats (owners, CCU, reviews)
- `market_snapshots` - Genre trends, top sellers
- `revenue_records` - Financial data from Partner API

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload --port 8080

# Run tests
pytest
```

## License

Private - First Break Labs
