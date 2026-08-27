# habibi-boost-3 - ProxRipper HTTPS ALL Booster

HTTPS proxy booster - ALL proxies (no 50k cap) from [ProxRipper](https://github.com/Mohammedcha/ProxRipper).

- **Source:** `https://raw.githubusercontent.com/Mohammedcha/ProxRipper/refs/heads/main/full_proxies/https.txt` - **ALL 56,927 HTTPS proxies (no cap)**
- **Pipeline:** Load persistent dead list -> fetch ALL HTTPS -> dead-first filter (remove already dead before validate) -> validate via `httpbin.org/ip` (100 concurrency) -> update dead list (never deleted) -> geolocate working via `ip-api.com/batch` -> save `data/live_proxies.json`, `data/dead_proxies.json`, `country/<CC>/https.txt`
- **Schedule:** Every 1 hour + manual dispatch
- **Dead list:** Persistent per repo (initially seeded from habibi-boost 49k)

## Data
- `data/dead_proxies.json` - persistent dead proxies (never deleted)
- `data/live_proxies.json` - working proxies with country
- `country/<CC>/https.txt` - per-country sorted (HTTPS)
- `country/all_https.txt` - all working HTTPS
