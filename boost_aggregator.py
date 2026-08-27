import asyncio
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DEAD_FILE = DATA_DIR / "dead_proxies.json"
LIVE_FILE = DATA_DIR / "live_proxies.json"
COUNTRY_DIR = ROOT / "country"

ADDRESS_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d{1,5})")
CONCURRENCY = 100
TIMEOUT = 10
PROXRIPPER_HTTPS = "https://raw.githubusercontent.com/Mohammedcha/ProxRipper/refs/heads/main/full_proxies/https.txt"

DATA_DIR.mkdir(parents=True, exist_ok=True)
COUNTRY_DIR.mkdir(parents=True, exist_ok=True)


def load_dead_set():
    if DEAD_FILE.exists():
        try:
            data = json.loads(DEAD_FILE.read_text(encoding="utf-8"))
            return set(data.get("dead", []))
        except Exception:
            return set()
    return set()


def save_dead_set(dead_set):
    save_data = {"dead": sorted(dead_set), "updated": time.time(), "count": len(dead_set)}
    DEAD_FILE.write_text(json.dumps(save_data, indent=2), encoding="utf-8")


async def test_proxy(proxy, semaphore):
    """Test if proxy is alive via httpbin.org/ip - HTTPS proxies also tested via http:// prefix"""
    async with semaphore:
        try:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(
                    "http://httpbin.org/ip",
                    proxy=f"http://{proxy}",
                    timeout=timeout,
                ) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            pass
    return False


async def geolocate_batch(ips):
    """Get country codes for IPs via ip-api.com batch API"""
    result = {}
    uniq_ips = list(dict.fromkeys(ips))
    batches = [uniq_ips[i:i+100] for i in range(0, len(uniq_ips), 100)]
    async with aiohttp.ClientSession() as s:
        for batch in batches:
            payload = [{"query": ip} for ip in batch]
            for attempt in range(3):
                try:
                    async with s.post(
                        "http://ip-api.com/batch",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for entry in data:
                                if isinstance(entry, dict) and entry.get("status") == "success":
                                    q = entry.get("query", "")
                                    cc = entry.get("countryCode", "").upper()
                                    if cc:
                                        result[q] = cc
                            break
                except Exception:
                    pass
                await asyncio.sleep(1)
            await asyncio.sleep(0.5)
    return result


async def main():
    print("[Boost-3 HTTPS] Starting ProxRipper HTTPS booster (ALL proxies, no cap)...")
    print(f"[Boost-3] Config: CONCURRENCY={CONCURRENCY}, TIMEOUT={TIMEOUT}s, SOURCE=HTTPS ALL")

    # 1. Load dead set (persistent, never deleted)
    dead_set = load_dead_set()
    print(f"[Boost-3] Loaded dead list: {len(dead_set)} proxies")

    # 2. Fetch ProxRipper HTTPS (ALL, no 50k cap)
    print("[Boost-3] Fetching ProxRipper HTTPS (ALL proxies)...")
    text = ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as sess:
            async with sess.get(
                PROXRIPPER_HTTPS,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                else:
                    print(f"[Boost-3] Fetch failed: HTTP {resp.status}")
                    return
    except Exception as e:
        print(f"[Boost-3] Fetch error: {e}")
        return

    if not text:
        print("[Boost-3] Empty response from ProxRipper")
        return

    # Parse ALL proxies - dedup while preserving order, no cap
    all_proxies = []
    seen = set()
    for line in text.splitlines():
        m = ADDRESS_RE.search(line)
        if m:
            p = m.group(1)
            if p not in seen:
                seen.add(p)
                all_proxies.append(p)

    proxies = all_proxies  # no cap, all HTTPS
    print(f"[Boost-3] Fetched {len(proxies)} unique HTTPS proxies (no cap, ALL)")

    if not proxies:
        print("[Boost-3] No proxies found, exiting")
        return

    # 3. Filter out already dead proxies (dead list is permanent)
    initial_count = len(proxies)
    filtered = [p for p in proxies if p not in dead_set]
    removed_dead = initial_count - len(filtered)
    print(f"[Boost-3] After dead filter: {initial_count} -> {len(filtered)} (removed {removed_dead} already dead)")

    if not filtered:
        print("[Boost-3] All proxies were in dead list, nothing to validate")
        save_dead_set(dead_set)
        return

    # 4. Validate proxies (concurrent)
    print(f"[Boost-3] Validating {len(filtered)} proxies (concurrency={CONCURRENCY})...")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [test_proxy(p, semaphore) for p in filtered]
    results = await asyncio.gather(*tasks)

    working = [p for p, ok in zip(filtered, results) if ok]
    dead_new = [p for p, ok in zip(filtered, results) if not ok]

    print(f"[Boost-3] Validation done -> Working: {len(working)}, Dead new: {len(dead_new)}")

    # 5. Update dead list (persistent, never deleted)
    if dead_new:
        dead_set.update(dead_new)
    save_dead_set(dead_set)
    print(f"[Boost-3] Dead list updated: {len(dead_set)} total (added {len(dead_new)})")

    # 6. Geolocate working proxies
    if working:
        print(f"[Boost-3] Geolocating {len(working)} working proxies...")
        ips = [p.split(":")[0] for p in working]
        country_map = await geolocate_batch(ips)
        print(f"[Boost-3] Geolocated {len(country_map)} IPs")
    else:
        country_map = {}
        print("[Boost-3] No working proxies to geolocate")

    # 7. Save live proxies with country
    live_data = []
    for p in working:
        ip = p.split(":")[0]
        country = country_map.get(ip, "XX")
        live_data.append({"proxy": p, "country": country})

    LIVE_FILE.write_text(
        json.dumps({"proxies": live_data, "count": len(live_data), "updated": time.time()}, indent=2),
        encoding="utf-8",
    )
    print(f"[Boost-3] Saved live list: {LIVE_FILE} ({len(live_data)} proxies)")

    # 8. Sort by country and save per-country files
    by_country = defaultdict(list)
    for entry in live_data:
        cc = entry.get("country", "XX") or "XX"
        by_country[cc].append(entry["proxy"])

    if COUNTRY_DIR.exists():
        for old in COUNTRY_DIR.glob("*"):
            if old.is_file():
                old.unlink()
            elif old.is_dir():
                for f in old.glob("*"):
                    if f.is_file():
                        f.unlink()

    for cc, plist in by_country.items():
        cc_dir = COUNTRY_DIR / cc
        cc_dir.mkdir(parents=True, exist_ok=True)
        (cc_dir / "https.txt").write_text("\n".join(plist) + "\n", encoding="utf-8")

    # Also save all working as single file (https)
    (COUNTRY_DIR / "all_https.txt").write_text("\n".join(working) + "\n" if working else "", encoding="utf-8")
    # Keep legacy all_http.txt for compatibility
    (COUNTRY_DIR / "all_http.txt").write_text("\n".join(working) + "\n" if working else "", encoding="utf-8")

    print("\n[Boost-3] DONE!")
    print(f"  Working: {len(working)}")
    print(f"  Dead (new): {len(dead_new)}")
    print(f"  Dead list total: {len(dead_set)}")
    print(f"  Countries: {len(by_country)} -> {sorted(by_country.keys())[:10]}")


if __name__ == "__main__":
    asyncio.run(main())
