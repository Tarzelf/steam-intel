# Steam Partner API - IP Whitelist Request

> Tutorial for getting your VPS IP whitelisted for Steam Partner API access

---

## What You Need

| Item | Value |
|------|-------|
| VPS IP Address | `91.99.63.4` |
| Server Provider | Hetzner Cloud |
| Server Location | Germany (Falkenstein) |
| Purpose | Steam Intel analytics service for First Break Labs |

---

## Why Whitelist?

The Steam Partner API provides access to:
- **Revenue data** - Sales, refunds, gross revenue
- **Regional breakdowns** - Sales by country
- **Package sales** - Bundle and DLC performance
- **Real-time sales** - Up-to-the-minute data

Without IP whitelisting, you only get public data (SteamSpy estimates, review counts, etc.).

---

## Step 1: Log into Steamworks

1. Go to https://partner.steamgames.com
2. Log in with your Steam account that has Publisher access
3. Navigate to **Users & Permissions** → **Manage Groups**

---

## Step 2: Find API Settings

1. Click on your publisher group (e.g., "First Break Labs")
2. Go to **Web API** section
3. Look for **"Allowed IP Addresses"** or **"Web API Key Settings"**

---

## Step 3: Add the VPS IP

Add this IP address to the whitelist:

```
91.99.63.4
```

**Note:** Some Steamworks interfaces require you to add IPs one at a time. If you need a range, use:
```
91.99.63.4/32
```
(This is CIDR notation for a single IP)

---

## Step 4: Generate/Confirm Partner API Key

1. In Steamworks, go to **Users & Permissions** → **Manage Groups**
2. Select your publisher group
3. Find **"Generate Web API Key"** or view existing key
4. Copy the Partner API Key

---

## Step 5: Update Steam Intel Config

Once you have the Partner API Key, I'll add it to the server:

```bash
# SSH into server
ssh deploy@91.99.63.4

# Edit the .env file
cd ~/apps/steam-intel
nano .env

# Add/update this line:
STEAM_PARTNER_KEY=your_partner_api_key_here
```

Then restart the service:
```bash
docker compose restart api
```

---

## Step 6: Verify Access

Test the Partner API endpoint:

```bash
curl -H "X-API-Key: YOUR_API_SECRET" \
  http://91.99.63.4:8080/api/v1/revenue/summary
```

If whitelisted correctly, you'll see revenue data. If not, you'll get an access denied error.

---

## Troubleshooting

### "Access Denied" after whitelisting

- **Wait 15-30 minutes** - Steamworks changes can take time to propagate
- **Check the exact IP** - Run `curl ifconfig.me` on the VPS to confirm
- **Verify key permissions** - Ensure the API key has "View Financial Info" permission

### Can't find whitelist settings

Contact Steam Partner support or your Steamworks admin. The interface varies based on your publisher tier.

### Multiple IPs needed

If you have multiple services or a load balancer, whitelist all egress IPs.

---

## Quick Reference

**Send this to Joe/Steamworks admin:**

```
Please whitelist the following IP for Steam Partner API access:

IP Address: 91.99.63.4
Publisher: First Break Labs
Purpose: Automated analytics collection for portfolio tracking
Server: Hetzner Cloud VPS (Germany)

Thank you!
```

---

## Security Notes

- The VPS IP is static (Hetzner dedicated IP)
- All API calls are authenticated with API key
- Revenue data is stored encrypted in PostgreSQL
- Only authorized FBL admin accounts can access the dashboard

---

## Contact

If you need help with this process, reach out to:
- **Tarzelf** - tarzelf@proton.me
- **Steam Partner Support** - https://partner.steamgames.com/support
