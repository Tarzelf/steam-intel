# Steam Intel API Documentation

> For app developers integrating with Steam Intel service

---

## Overview

Steam Intel is a REST API that provides Steam game analytics, market intelligence, and portfolio tracking for First Break Labs.

**Base URL:** `http://91.99.63.4:8080` (direct) or `https://api.alorfutures.com/steam` (via Traefik)

**Authentication:** All endpoints require `X-API-Key` header

---

## Authentication

Every request must include the API key in the header:

```bash
X-API-Key: 1d23f0772f73ad1926f6f9bffac96be9ded2494800a303edb146e1f0fbfcb8c3
```

**Example:**
```bash
curl -H "X-API-Key: YOUR_API_KEY" http://91.99.63.4:8080/api/v1/portfolio
```

---

## Data Persistence

**Yes, all data is saved locally!** The service maintains historical data in PostgreSQL:

| Table | Purpose | Update Frequency |
|-------|---------|------------------|
| `games` | Game metadata (name, developer, price, tags) | On first fetch |
| `game_snapshots` | Point-in-time stats (CCU, reviews, owners) | Every 6 hours |
| `genre_snapshots` | Genre market data | Daily |
| `genre_scores` | Genre fitness scores | Weekly |
| `top_sellers_snapshots` | Steam top sellers lists | Daily |
| `revenue_records` | Sales & revenue data | Daily (requires Partner API) |

---

## Endpoints

### Health Check

```http
GET /health
```

No authentication required.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-10T01:25:39.466100",
  "service": "steam-intel"
}
```

---

## Portfolio Endpoints

### Get Portfolio Summary

```http
GET /api/v1/portfolio
```

Returns current stats for all First Break Labs games.

**Response:**
```json
{
  "total_games": 9,
  "total_ccu": 44,
  "total_reviews": 1672,
  "avg_review_score": 52.9,
  "games": [
    {
      "app_id": 2602030,
      "name": "Entropy Survivors",
      "developer": "Moving Pieces Interactive",
      "release_date": null,
      "price": 9.99,
      "owners_min": 0,
      "owners_max": 20000,
      "ccu": 33,
      "reviews_positive": 272,
      "reviews_negative": 55,
      "review_score": 83,
      "avg_playtime_hours": 6.33,
      "snapshot_date": "2026-01-10"
    }
    // ... more games
  ]
}
```

---

### Get Single Game Stats

```http
GET /api/v1/portfolio/{app_id}
```

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `app_id` | int | Steam App ID |

**Example:**
```bash
curl -H "X-API-Key: YOUR_KEY" http://91.99.63.4:8080/api/v1/portfolio/2602030
```

**Response:**
```json
{
  "app_id": 2602030,
  "name": "Entropy Survivors",
  "developer": "Moving Pieces Interactive",
  "release_date": null,
  "price": 9.99,
  "owners_min": 0,
  "owners_max": 20000,
  "ccu": 33,
  "reviews_positive": 272,
  "reviews_negative": 55,
  "review_score": 83,
  "avg_playtime_hours": 6.33,
  "snapshot_date": "2026-01-10"
}
```

---

### Get Game History

```http
GET /api/v1/portfolio/{app_id}/history?period=30d
```

Returns historical stats for trend analysis.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `app_id` | int | required | Steam App ID |
| `period` | string | `30d` | Time period (e.g., `7d`, `30d`, `90d`) |

**Response:**
```json
[
  {
    "date": "2026-01-01",
    "ccu": 45,
    "reviews_positive": 250,
    "reviews_negative": 50,
    "review_score": 83
  },
  {
    "date": "2026-01-02",
    "ccu": 42,
    "reviews_positive": 255,
    "reviews_negative": 51,
    "review_score": 83
  }
  // ... more data points
]
```

---

### Get Week-over-Week Changes

```http
GET /api/v1/portfolio/{app_id}/wow
```

Returns week-over-week comparison.

**Response:**
```json
{
  "app_id": 2602030,
  "current_date": "2026-01-10",
  "previous_date": "2026-01-03",
  "ccu": {
    "current": 33,
    "previous": 45,
    "change_pct": -26.7
  },
  "reviews": {
    "current": 327,
    "new_this_week": 12
  },
  "review_score": {
    "current": 83,
    "previous": 82,
    "change": 1
  }
}
```

---

## Market Intelligence Endpoints

### Get All Genre Stats

```http
GET /api/v1/market/genres
```

Returns latest stats for all tracked genres.

**Response:**
```json
[
  {
    "genre": "roguelike",
    "game_count": 1250,
    "total_ccu": 45000,
    "avg_ccu": 36,
    "avg_review_score": 78,
    "top_games": ["Hades", "Slay the Spire", "Dead Cells"],
    "snapshot_date": "2026-01-10"
  }
]
```

---

### Get Single Genre Stats

```http
GET /api/v1/market/genres/{genre}
```

**Example:**
```bash
curl -H "X-API-Key: YOUR_KEY" http://91.99.63.4:8080/api/v1/market/genres/roguelike
```

---

### Get Genre Fitness Score

```http
GET /api/v1/market/genres/{genre}/score
```

Returns market fitness score for evaluating game submissions.

**Response:**
```json
{
  "genre": "roguelike",
  "hotness_score": 75,
  "saturation_score": 60,
  "success_rate_score": 70,
  "timing_score": 80,
  "overall_score": 71,
  "recommendation": "hot",
  "score_date": "2026-01-10"
}
```

**Score meanings:**
- `hotness_score`: How popular is the genre right now (0-100)
- `saturation_score`: How crowded is the market (lower = more crowded)
- `success_rate_score`: % of games in genre with positive reviews
- `timing_score`: Is it a good time to release in this genre
- `recommendation`: `hot`, `warm`, `cold`, or `unknown`

---

### Get Trending Genres

```http
GET /api/v1/market/trending
```

Returns genres with growing player counts.

**Response:**
```json
[
  {
    "genre": "survival",
    "current_ccu": 125000,
    "previous_ccu": 100000,
    "change_pct": 25.0,
    "direction": "up"
  }
]
```

---

### Get Top Sellers

```http
GET /api/v1/market/top-sellers?category=top_sellers
```

**Parameters:**
| Name | Type | Default | Options |
|------|------|---------|---------|
| `category` | string | `top_sellers` | `top_sellers`, `specials`, `new_releases` |

**Response:**
```json
[
  {
    "category": "top_sellers",
    "snapshot_date": "2026-01-10",
    "rankings": [
      {"rank": 1, "app_id": 1234, "name": "Game Name"},
      {"rank": 2, "app_id": 5678, "name": "Another Game"}
    ]
  }
]
```

---

## Analysis Endpoints

### Analyze a Game

```http
POST /api/v1/analyze/game
Content-Type: application/json

{
  "app_id": 1234567
}
```

Fetches fresh data from Steam and returns full analysis.

**Response:**
```json
{
  "app_id": 1234567,
  "name": "Game Name",
  "developer": "Developer Studio",
  "publisher": "Publisher Name",
  "price": 19.99,
  "genres": ["Action", "Indie"],
  "tags": ["roguelike", "pixel-graphics", "difficult"],
  "owners_estimate": "20,000 - 50,000",
  "ccu": 150,
  "avg_playtime_hours": 12.5,
  "review_score": 85,
  "total_reviews": 500,
  "genre_scores": [
    {
      "genre": "roguelike",
      "hotness": 75,
      "saturation": 60,
      "overall": 71,
      "recommendation": "hot"
    }
  ],
  "comparable_games": [
    {
      "app_id": 9999,
      "name": "Similar Game",
      "tags": ["roguelike", "pixel-graphics"],
      "tag_overlap": 2,
      "ccu": 200,
      "owners": "50,000 - 100,000",
      "review_score": 90,
      "price": 14.99
    }
  ],
  "market_fit_score": 78,
  "assessment": "Strong market fit based on genre trends. Excellent player reception. Healthy concurrent player count. Tags in hot genres: roguelike."
}
```

---

### Find Comparable Games

```http
POST /api/v1/analyze/comparable
Content-Type: application/json

{
  "tags": ["roguelike", "indie", "pixel-graphics"],
  "price_min": 10,
  "price_max": 20
}
```

Finds games with similar tags and price range.

**Response:**
```json
[
  {
    "app_id": 9999,
    "name": "Similar Game",
    "tags": ["roguelike", "indie", "difficult"],
    "tag_overlap": 2,
    "ccu": 200,
    "owners": "50,000 - 100,000",
    "review_score": 90,
    "price": 14.99
  }
]
```

---

## Revenue Endpoints

> **Note:** Revenue endpoints require Steam Partner API access. Contact Joe to whitelist VPS IP: `91.99.63.4`

### Get Revenue Summary

```http
GET /api/v1/revenue/summary?period=30d
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `period` | string | `30d` | Time period (e.g., `7d`, `30d`, `90d`) |

**Response:**
```json
{
  "total_gross_cents": 5000000,
  "total_net_cents": 3500000,
  "total_units": 2500,
  "period_start": "2025-12-10",
  "period_end": "2026-01-10",
  "by_game": [
    {
      "app_id": 2602030,
      "name": "Entropy Survivors",
      "gross_cents": 2500000,
      "net_cents": 1750000,
      "units": 1500
    }
  ]
}
```

---

### Get Game Revenue

```http
GET /api/v1/revenue/{app_id}?period=90d
```

**Response:**
```json
{
  "app_id": 2602030,
  "name": "Entropy Survivors",
  "total_gross_cents": 5000000,
  "total_net_cents": 3500000,
  "total_units": 2500,
  "periods": [
    {
      "period_start": "2025-12-01",
      "period_end": "2025-12-31",
      "period_type": "monthly",
      "gross_cents": 3000000,
      "net_cents": 2100000,
      "units": 1500,
      "refunds": 25
    }
  ]
}
```

---

### Upload Revenue CSV

```http
POST /api/v1/revenue/upload
Content-Type: multipart/form-data

file: <steamworks_revenue.csv>
```

Manually import Steamworks revenue CSV export.

**Response:**
```json
{
  "imported": 12,
  "message": "Successfully imported 12 revenue records"
}
```

---

## Admin Endpoints

### Manually Trigger Portfolio Collection

```http
POST /api/v1/admin/collect/portfolio
```

Forces immediate data collection (normally runs every 6 hours).

**Response:**
```json
{
  "status": "completed",
  "job": "portfolio_stats"
}
```

---

### Manually Trigger Market Collection

```http
POST /api/v1/admin/collect/market
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

**Common errors:**

| Status | Meaning |
|--------|---------|
| 401 | Missing or invalid API key |
| 404 | Game or resource not found |
| 400 | Invalid request (bad parameters) |
| 500 | Server error |

---

## Code Examples

### JavaScript/TypeScript

```typescript
const API_BASE = 'http://91.99.63.4:8080';
const API_KEY = 'your_api_key_here';

async function getPortfolio() {
  const response = await fetch(`${API_BASE}/api/v1/portfolio`, {
    headers: {
      'X-API-Key': API_KEY,
    },
  });
  return response.json();
}

async function analyzeGame(appId: number) {
  const response = await fetch(`${API_BASE}/api/v1/analyze/game`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ app_id: appId }),
  });
  return response.json();
}
```

### Python

```python
import requests

API_BASE = 'http://91.99.63.4:8080'
API_KEY = 'your_api_key_here'
HEADERS = {'X-API-Key': API_KEY}

def get_portfolio():
    response = requests.get(f'{API_BASE}/api/v1/portfolio', headers=HEADERS)
    return response.json()

def get_game_history(app_id: int, period: str = '30d'):
    response = requests.get(
        f'{API_BASE}/api/v1/portfolio/{app_id}/history',
        params={'period': period},
        headers=HEADERS
    )
    return response.json()
```

### cURL

```bash
# Get portfolio
curl -H "X-API-Key: YOUR_KEY" http://91.99.63.4:8080/api/v1/portfolio

# Get game history
curl -H "X-API-Key: YOUR_KEY" "http://91.99.63.4:8080/api/v1/portfolio/2602030/history?period=30d"

# Analyze a game
curl -X POST \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"app_id": 1234567}' \
  http://91.99.63.4:8080/api/v1/analyze/game
```

---

## Rate Limits

Currently no rate limits are enforced, but please be reasonable:
- Portfolio/market data: Cache for at least 5 minutes
- Analysis requests: Max 10/minute (fetches fresh data from Steam)
- History queries: No limit

---

## Data Collection Schedule

| Job | Frequency | Data Source |
|-----|-----------|-------------|
| Portfolio Stats | Every 6 hours | SteamSpy API |
| Market Trends | Daily | Steam Store API |
| Genre Analysis | Weekly | SteamSpy + analysis |
| Revenue Sync | Daily | Steam Partner API |

---

## Contact

- **API Issues:** tarzelf@proton.me
- **Interactive Docs:** http://91.99.63.4:8080/docs (Swagger UI)
