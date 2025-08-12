# pip install ccxt python-dotenv
import os, json, time, argparse
from datetime import datetime, timezone
import ccxt
from dotenv import load_dotenv

STABLES = {"USDT","USDC","TUSD","DAI","FDUSD","USD"}
FIAT_CODES = {"BRL", "BRLT", "BRLZ"}  # tolerate aliases

def _init_bybit_from_env(testnet=False):
    load_dotenv()
    key, secret = os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
    ex = ccxt.bybit({"apiKey": key, "secret": secret, "enableRateLimit": True, "options": {"defaultType": "spot"}})
    if testnet: ex.set_sandbox_mode(True)
    ex.load_markets()
    return ex


FIAT_CODES = {"BRL", "BRLT", "BRLZ"}  # keep aliases

def _fetch_fiat_convert_7d(ex):
    """
    Proxy for fiat top-ups: capture BRL->crypto conversions from Convert/One-Click Buy.
    GET /v5/asset/exchange/order-record
    """
    now_ms   = int(time.time()*1000)
    since_ms = now_ms - 7*24*60*60*1000
    rows, cursor = [], None

    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        res = ex.request("v5/asset/exchange/order-record", "private", "GET", params)
        result = (res or {}).get("result") or {}
        page = result.get("orderBody") or []
        for r in page:
            # createdTime is seconds -> ms
            ct = int(r.get("createdTime", "0"))
            ts_ms = ct * 1000 if ct < 10_000_000_000 else ct
            if ts_ms < since_ms or ts_ms > now_ms:
                continue
            from_coin = (r.get("fromCoin") or "").upper()
            to_coin   = (r.get("toCoin") or "").upper()
            from_amt  = float(r.get("fromAmount") or 0.0)
            to_amt    = float(r.get("toAmount") or 0.0)
            if from_coin not in FIAT_CODES or from_amt <= 0:
                continue
            rows.append({
                "id": r.get("exchangeTxId"),
                "txid": r.get("exchangeTxId"),
                "type": "fiat_convert",
                "timestamp": ts_ms,
                "datetime": datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).isoformat(),
                "currency": from_coin,              # BRL side
                "amount": from_amt,                 # BRL amount spent
                "status": "ok",
                "network": None,
                "to_coin": to_coin,
                "to_amount": to_amt,
            })
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return rows

def _fetch_onchain_deposits_7d(ex):
    now_ms = int(time.time()*1000)
    since_ms = now_ms - 7*24*60*60*1000
    rows, cursor = [], None

    # Prefer unified if available
    if ex.has.get("fetchDeposits"):
        while True:
            params = {"startTime": since_ms, "endTime": now_ms, "limit": 50}
            if cursor: params["cursor"] = cursor
            page = ex.fetch_deposits(since=since_ms, limit=50, params=params)
            rows.extend(page)
            nxt = None
            if page and isinstance(page[0], dict):
                info = page[0].get("info")
                if isinstance(info, dict): nxt = info.get("nextPageCursor")
            if not nxt: break
            cursor = nxt
        return rows

    # Fallback via request()
    while True:
        params = {"startTime": since_ms, "endTime": now_ms, "limit": 50}
        if cursor: params["cursor"] = cursor
        res = ex.request("v5/asset/deposit/query-record", "private", "GET", params)
        result = (res or {}).get("result") or {}
        for r in result.get("rows") or []:
            ts = int(r.get("successAt") or r.get("createdTime") or now_ms)
            rows.append({
                "id": r.get("id"),
                "txid": r.get("txID"),
                "type": "deposit",
                "timestamp": ts,
                "datetime": datetime.fromtimestamp(ts/1000, tz=timezone.utc).isoformat(),
                "currency": ex.safe_currency_code(r.get("coin")),
                "amount": float(r.get("amount") or 0.0),
                "status": {1:"pending",2:"ok",3:"failed"}.get(int(r.get("status",3)), "ok"),
                "network": r.get("chain"),
            })
        cursor = result.get("nextPageCursor")
        if not cursor: break
    return rows

def _fetch_internal_deposits_7d(ex):
    """Fiat/on‑platform deposits (off‑chain). GET /v5/asset/deposit/query-internal-record"""
    now_ms   = int(time.time() * 1000)
    since_ms = now_ms - 7 * 24 * 60 * 60 * 1000
    rows, cursor = [], None

    while True:
        params = {"startTime": since_ms, "endTime": now_ms, "limit": 50}
        if cursor:
            params["cursor"] = cursor

        # version-proof call
        res    = ex.request("v5/asset/deposit/query-internal-record", "private", "GET", params)
        result = (res or {}).get("result") or {}
        page   = result.get("rows") or []
        for r in page:
            # createdTime is **seconds** string per docs; convert to ms
            ct_raw = r.get("createdTime")
            if ct_raw is None:
                ts_ms = now_ms
            else:
                ct = int(ct_raw)
                ts_ms = ct * 1000 if ct < 10_000_000_000 else ct  # handle seconds vs ms defensively
            rows.append({
                "id": r.get("id"),
                "txid": r.get("txID"),
                "type": "internal_deposit",
                "timestamp": ts_ms,
                "datetime": datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).isoformat(),
                "currency": ex.safe_currency_code(r.get("coin")),
                "amount": float(r.get("amount") or 0.0),
                "status": {1: "processing", 2: "ok", 3: "failed"}.get(int(r.get("status", 2)), "ok"),
                "network": None,
            })
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return rows
def _ohlcv_close(ex, symbol, ts_ms):
    candles = ex.fetch_ohlcv(symbol, timeframe="1m", since=ts_ms - 60_000, limit=2)
    if not candles:
        raise ValueError(f"No OHLCV for {symbol} near {ts_ms}")
    return float(candles[-1][4])

def _price_usd_at(ex, code, ts_ms):
    code = (code or "").upper()
    if code in STABLES: return 1.0
    if code in FIAT_CODES:
        if "USDT/BRL" in ex.markets:
            px = _ohlcv_close(ex, "USDT/BRL", ts_ms)   # BRL per USDT
            return 1.0 / px                            # USD per BRL
        if "BRL/USDT" in ex.markets:
            return _ohlcv_close(ex, "BRL/USDT", ts_ms) # USDT per BRL ~= USD per BRL
        raise ValueError("No USDT/BRL or BRL/USDT market")
    # crypto
    sym = f"{code}/USDT"
    if sym in ex.markets: return _ohlcv_close(ex, sym, ts_ms)
    inv = f"USDT/{code}"
    if inv in ex.markets:
        px = _ohlcv_close(ex, inv, ts_ms)
        return 1.0 / px if px else float("nan")
    alt = f"{code}/USDC"
    if alt in ex.markets: return _ohlcv_close(ex, alt, ts_ms)
    raise ValueError(f"No USD pricing path for {code}")


def _print_table(entries, total):
    headers = ["Datetime(UTC)","Cur","Amount","USD_px@time","USD_value","Txid","Source"]
    widths  = [20,5,14,14,14,20,10]
    print("  ".join(h.ljust(widths[i]) for i,h in enumerate(headers)))
    print("-"*sum(widths))
    for e in entries:
        row = [
            e["datetime"][:widths[0]].ljust(widths[0]),
            e["currency"].ljust(widths[1]),
            f'{e["amount"]:,.8f}'[:widths[2]].rjust(widths[2]),
            f'{e["usd_px_at_time"]:,.6f}'[:widths[3]].rjust(widths[3]),
            f'{e["usd_value"]:,.2f}'[:widths[4]].rjust(widths[4]),
            (e.get("txid") or "")[:widths[5]].ljust(widths[5]),
            e["source"][:widths[6]].ljust(widths[6]),
        ]
        print("  ".join(row))
    print("\nTOTAL (7d) USD:", f"{total:,.2f}")

def deposits_last_7d(testnet=False):
    ex = _init_bybit_from_env(testnet)
    onchain   = _fetch_onchain_deposits_7d(ex)      # crypto on-chain
    internal  = _fetch_internal_deposits_7d(ex)     # in-platform transfers (often 0)
    fiat_conv = _fetch_fiat_convert_7d(ex)          # BRL -> crypto buys (proxy for fiat top-ups)

    seen, merged = set(), []
    for src, arr in (("onchain", onchain), ("internal", internal), ("fiat_convert", fiat_conv)):
        for t in arr:
            key = (src, t.get("id") or t.get("txid"))
            if key in seen: 
                continue
            seen.add(key)
            merged.append({**t, "source": src})

    # Keep: onchain (non-fiat) + fiat_convert (BRL aliases) + internal (BRL aliases, if any)
    filtered = []
    for t in merged:
        code = (t.get("currency") or "").upper()
        if t["source"] == "onchain" and code not in FIAT_CODES:
            filtered.append(t)
        elif t["source"] in ("fiat_convert", "internal") and code in FIAT_CODES:
            filtered.append(t)    # Convert to USD at time
    entries, total = [], 0.0
    for t in filtered:
        if t.get("status") not in ("ok","processing","pending"):
            continue
        amt = float(t.get("amount") or 0.0)
        if amt <= 0: continue
        ts = int(t.get("timestamp") or 0)
        try:
            usd_per_unit = _price_usd_at(ex, t["currency"], ts)
        except Exception:
            continue
        usd_val = amt * usd_per_unit
        total += usd_val
        entries.append({
            "datetime": t["datetime"],
            "currency": t["currency"],
            "amount": amt,
            "usd_px_at_time": usd_per_unit,
            "usd_value": usd_val,
            "txid": t.get("txid"),
            "id": t.get("id"),
            "network": t.get("network"),
            "source": t["source"],
        })
    # sort by time asc
    entries.sort(key=lambda x: x["datetime"])
    return entries, total

def main():
    ap = argparse.ArgumentParser(description="Bybit deposits (last 7d). Includes on-chain crypto + internal fiat. USD at deposit time.")
    ap.add_argument("--out", required=True, help="Path to write JSON output")
    ap.add_argument("--testnet", action="store_true", help="Use Bybit testnet/sandbox")
    args = ap.parse_args()

    entries, total = deposits_last_7d(testnet=args.testnet)
    _print_table(entries, total)
    payload = {
        "generated_at_utc": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "window_days": 7,
        "entries": entries,
        "total_usd_7d": total,
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nJSON written: {args.out}")

if __name__ == "__main__":
    main()




