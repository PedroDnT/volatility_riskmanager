#!/usr/bin/env python3
# bybit_account_tools.py
# pip install ccxt python-dotenv

import os, json, time, argparse
from datetime import datetime, timezone
import ccxt
from dotenv import load_dotenv

# ====== Config / constants ======
STABLES = {"USDT", "USDC", "TUSD", "DAI", "FDUSD", "USD"}
FIAT_CODES = {"BRL", "BRLT", "BRLZ"}  # tolerate aliases for BRL

# ====== Common helpers ======

def _init_bybit_from_env(testnet: bool = False) -> ccxt.bybit:
    load_dotenv()
    key, secret = os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
    ex = ccxt.bybit({
        "apiKey": key,
        "secret": secret,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    if testnet:
        ex.set_sandbox_mode(True)
    ex.load_markets()
    return ex

def _ms_7d_window():
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - 7 * 24 * 60 * 60 * 1000
    return since_ms, now_ms

def _ohlcv_close(ex: ccxt.bybit, symbol: str, ts_ms: int) -> float:
    candles = ex.fetch_ohlcv(symbol, timeframe="1m", since=ts_ms - 60_000, limit=2)
    if not candles:
        raise ValueError(f"No OHLCV for {symbol} near {ts_ms}")
    return float(candles[-1][4])

def _price_usd_at(ex: ccxt.bybit, code: str, ts_ms: int) -> float:
    """
    USD per 1 unit of `code` at ts_ms.
    - Stables -> 1
    - BRL -> invert USDT/BRL or use BRL/USDT
    - Crypto -> CODE/USDT (or inverse/USDC)
    """
    code = (code or "").upper()
    if code in STABLES:
        return 1.0
    if code in FIAT_CODES:
        if "USDT/BRL" in ex.markets:
            px = _ohlcv_close(ex, "USDT/BRL", ts_ms)  # BRL per USDT
            if px <= 0:
                raise ValueError("Bad USDT/BRL price")
            return 1.0 / px                           # USD per BRL
        if "BRL/USDT" in ex.markets:
            px = _ohlcv_close(ex, "BRL/USDT", ts_ms)  # USDT per BRL
            if px <= 0:
                raise ValueError("Bad BRL/USDT price")
            return px                                 # USDT per BRL ~= USD per BRL
        raise ValueError("No BRL market available")

    # Crypto
    sym = f"{code}/USDT"
    if sym in ex.markets:
        return _ohlcv_close(ex, sym, ts_ms)
    inv = f"USDT/{code}"
    if inv in ex.markets:
        px = _ohlcv_close(ex, inv, ts_ms)
        return 1.0 / px if px else float("nan")
    alt = f"{code}/USDC"
    if alt in ex.markets:
        return _ohlcv_close(ex, alt, ts_ms)
    raise ValueError(f"No USD pricing for {code}")

def _format_dt(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

# ====== Deposits: on-chain, internal (rare), and fiat-proxy via Convert ======

def _fetch_onchain_deposits_7d(ex: ccxt.bybit):
    since_ms, now_ms = _ms_7d_window()
    rows, cursor = [], None

    # Prefer unified if CCXT supports it
    if ex.has.get("fetchDeposits"):
        while True:
            params = {"startTime": since_ms, "endTime": now_ms, "limit": 50}
            if cursor:
                params["cursor"] = cursor
            page = ex.fetch_deposits(since=since_ms, limit=50, params=params)
            rows.extend(page or [])
            nxt = None
            if page and isinstance(page[0], dict):
                info = page[0].get("info")
                if isinstance(info, dict):
                    nxt = info.get("nextPageCursor")
            if not nxt:
                break
            cursor = nxt
        # Normalize to our schema if coming from unified
        norm = []
        for t in rows:
            ts = int(t.get("timestamp") or 0)
            if ts == 0:
                continue
            norm.append({
                "id": t.get("id"),
                "txid": t.get("txid"),
                "type": "deposit",
                "timestamp": ts,
                "datetime": _format_dt(ts),
                "currency": (t.get("currency") or "").upper(),
                "amount": float(t.get("amount") or 0.0),
                "status": t.get("status") or "ok",
                "network": t.get("network"),
            })
        return norm

    # Fallback: call v5 directly
    while True:
        params = {"startTime": since_ms, "endTime": now_ms, "limit": 50}
        if cursor:
            params["cursor"] = cursor
        res = ex.request("v5/asset/deposit/query-record", "private", "GET", params)
        result = (res or {}).get("result") or {}
        for r in result.get("rows") or []:
            # successAt may be ms (string). Be defensive (sec vs ms).
            t_raw = r.get("successAt") or r.get("createdTime")
            if t_raw is None:
                continue
            ts = int(t_raw)
            ts = ts * 1000 if ts < 10_000_000_000 else ts
            rows.append({
                "id": r.get("id"),
                "txid": r.get("txID"),
                "type": "deposit",
                "timestamp": ts,
                "datetime": _format_dt(ts),
                "currency": ex.safe_currency_code(r.get("coin")),
                "amount": float(r.get("amount") or 0.0),
                "status": {1:"pending",2:"ok",3:"failed"}.get(int(r.get("status",3)), "ok"),
                "network": r.get("chain"),
            })
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return rows

def _fetch_internal_deposits_7d(ex: ccxt.bybit):
    """In-platform deposits (email/phone transfers). Often empty for fiat top-ups."""
    since_ms, now_ms = _ms_7d_window()
    rows, cursor = [], None
    while True:
        params = {"startTime": since_ms, "endTime": now_ms, "limit": 50}
        if cursor:
            params["cursor"] = cursor
        res = ex.request("v5/asset/deposit/query-internal-record", "private", "GET", params)
        result = (res or {}).get("result") or {}
        for r in result.get("rows") or []:
            ct_raw = r.get("createdTime")
            if ct_raw is None:
                continue
            ct = int(ct_raw)
            ts_ms = ct * 1000 if ct < 10_000_000_000 else ct
            rows.append({
                "id": r.get("id"),
                "txid": r.get("txID"),
                "type": "internal_deposit",
                "timestamp": ts_ms,
                "datetime": _format_dt(ts_ms),
                "currency": ex.safe_currency_code(r.get("coin")),
                "amount": float(r.get("amount") or 0.0),
                "status": {1: "processing", 2: "ok", 3: "failed"}.get(int(r.get("status", 2)), "ok"),
                "network": None,
            })
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return rows

def _fetch_fiat_convert_7d(ex: ccxt.bybit):
    """
    Proxy for fiat top-ups: capture BRL->crypto conversions (Convert / One-Click Buy).
    GET /v5/asset/exchange/order-record
    """
    since_ms, now_ms = _ms_7d_window()
    rows, cursor = [], None
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        res = ex.request("v5/asset/exchange/order-record", "private", "GET", params)
        result = (res or {}).get("result") or {}
        page = result.get("orderBody") or []
        for r in page:
            ct_raw = r.get("createdTime", "0")
            if ct_raw is None:
                continue
            ct = int(ct_raw)
            ts_ms = ct * 1000 if ct < 10_000_000_000 else ct
            if not (since_ms <= ts_ms <= now_ms):
                continue
            from_coin = (r.get("fromCoin") or "").upper()
            to_coin   = (r.get("toCoin") or "").upper()
            from_amt  = float(r.get("fromAmount") or 0.0)  # fiat BRL spent
            to_amt    = float(r.get("toAmount") or 0.0)    # crypto received
            if from_coin not in FIAT_CODES or from_amt <= 0:
                continue
            rows.append({
                "id": r.get("exchangeTxId"),
                "txid": r.get("exchangeTxId"),
                "type": "fiat_convert",
                "timestamp": ts_ms,
                "datetime": _format_dt(ts_ms),
                "currency": from_coin,
                "amount": from_amt,       # BRL amount
                "status": "ok",
                "network": None,
                "to_coin": to_coin,
                "to_amount": to_amt,
            })
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return rows

def _print_deposits_table(entries, total_usd):
    headers = ["Datetime(UTC)", "Cur", "Amount", "USD_px@time", "USD_value", "Txid", "Source"]
    widths  = [20,             6,     16,       14,            14,          22,     12]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-" * (sum(widths) + (len(widths)-1)*2))
    for e in entries:
        row = [
            (e["datetime"] or "")[:widths[0]].ljust(widths[0]),
            (e["currency"] or "")[:widths[1]].ljust(widths[1]),
            f'{e.get("amount",0):,.8f}'[:widths[2]].rjust(widths[2]),
            f'{e.get("usd_px_at_time",0):,.6f}'[:widths[3]].rjust(widths[3]),
            f'{e.get("usd_value",0):,.2f}'[:widths[4]].rjust(widths[4]),
            (e.get("txid") or "")[:widths[5]].ljust(widths[5]),
            (e.get("source") or "")[:widths[6]].ljust(widths[6]),
        ]
        print("  ".join(row))
    print("\nTOTAL (7d) USD:", f"{total_usd:,.2f}")

def cmd_deposits(args):
    ex = _init_bybit_from_env(args.testnet)
    onchain   = _fetch_onchain_deposits_7d(ex)      # crypto on-chain
    internal  = _fetch_internal_deposits_7d(ex)     # email/phone in-platform transfers
    fiat_conv = _fetch_fiat_convert_7d(ex)          # BRL->crypto (proxy for fiat top-ups)

    # Merge & dedupe
    seen, merged = set(), []
    for src, arr in (("onchain", onchain), ("internal", internal), ("fiat_convert", fiat_conv)):
        for t in arr:
            key = (src, t.get("id") or t.get("txid"))
            if key in seen:
                continue
            seen.add(key)
            merged.append({**t, "source": src})

    # Keep: onchain (non-fiat) + fiat_convert (BRL) + internal (BRL, if any)
    filtered = []
    for t in merged:
        code = (t.get("currency") or "").upper()
        if t["source"] == "onchain" and code not in FIAT_CODES:
            filtered.append(t)
        elif t["source"] in ("fiat_convert", "internal") and code in FIAT_CODES:
            filtered.append(t)

    # Convert to USD at event time
    entries, total = [], 0.0
    for t in filtered:
        status = t.get("status")
        if status not in ("ok", "processing", "pending"):
            continue
        amt = float(t.get("amount") or 0.0)
        if amt <= 0:
            continue
        ts = int(t.get("timestamp") or 0)
        try:
            usd_per_unit = _price_usd_at(ex, t["currency"], ts)
        except Exception:
            continue
        usd_val = amt * usd_per_unit
        total += usd_val
        entries.append({
            "datetime": t["datetime"],
            "currency": (t["currency"] or "").upper(),
            "amount": amt,
            "usd_px_at_time": usd_per_unit,
            "usd_value": usd_val,
            "txid": t.get("txid"),
            "id": t.get("id"),
            "network": t.get("network"),
            "source": t["source"],
            **({"to_coin": t.get("to_coin"), "to_amount": t.get("to_amount")} if "to_coin" in t else {}),
        })

    entries.sort(key=lambda x: x["datetime"] or "")
    _print_deposits_table(entries, total)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_days": 7,
        "entries": entries,
        "total_usd_7d": total,
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nJSON written: {args.out}")

# ====== PnL (closed + open) by settlement currency ======

def _fetch_closed_pnl_7d(ex: ccxt.bybit):
    """
    Realized PnL for closed positions in last 7d via:
    GET /v5/position/closed-pnl/list  (category in {linear, inverse})
    Returns list[ { currency, symbol, side, closedPnl, createdTime, ... } ]
    """
    since_ms, now_ms = _ms_7d_window()
    out = []
    for category in ("linear", "inverse"):
        cursor = None
        while True:
            params = {"category": category, "limit": 50}
            if cursor:
                params["cursor"] = cursor
            res = ex.request("v5/position/closed-pnl/list", "private", "GET", params)
            result = (res or {}).get("result") or {}
            for r in result.get("list") or []:
                ct_raw = r.get("createdTime")
                if not ct_raw:
                    continue
                ct = int(ct_raw)
                ts_ms = ct * 1000 if ct < 10_000_000_000 else ct
                if not (since_ms <= ts_ms <= now_ms):
                    continue
                # Bybit reports pnl in settlement currency for the instrument
                pnl = float(r.get("closedPnl") or 0.0)
                currency = (r.get("settleCoin") or r.get("symbol", "").split("-")[-1] or "USDT").upper()
                out.append({
                    "category": category,
                    "symbol": r.get("symbol"),
                    "side": r.get("side"),
                    "currency": currency,
                    "closed_pnl": pnl,
                    "timestamp": ts_ms,
                    "datetime": _format_dt(ts_ms),
                })
            cursor = result.get("nextPageCursor")
            if not cursor:
                break
    return out

def _fetch_open_positions_unrealized(ex: ccxt.bybit):
    """
    Unrealized PnL for current open positions via:
    GET /v5/position/list  (category in {linear, inverse})
    Summed per settlement currency.
    """
    out = []
    for category in ("linear", "inverse"):
        cursor = None
        while True:
            params = {"category": category, "limit": 50}
            if cursor:
                params["cursor"] = cursor
            res = ex.request("v5/position/list", "private", "GET", params)
            result = (res or {}).get("result") or {}
            for r in result.get("list") or []:
                # unrealisedPnl may be string; 0 when flat
                upnl = float(r.get("unrealisedPnl") or 0.0)
                if abs(upnl) < 1e-18:
                    continue
                currency = (r.get("settleCoin") or r.get("symbol", "").split("-")[-1] or "USDT").upper()
                ts_ms = int(time.time() * 1000)
                out.append({
                    "category": category,
                    "symbol": r.get("symbol"),
                    "side": r.get("side"),
                    "currency": currency,
                    "unrealized_pnl": upnl,
                    "timestamp": ts_ms,
                    "datetime": _format_dt(ts_ms),
                })
            cursor = result.get("nextPageCursor")
            if not cursor:
                break
    return out

def _group_currency_pnl(closed_rows, open_rows):
    by_ccy = {}
    for r in closed_rows:
        ccy = r["currency"]
        by_ccy.setdefault(ccy, {"closed": 0.0, "open": 0.0})
        by_ccy[ccy]["closed"] += r["closed_pnl"]
    for r in open_rows:
        ccy = r["currency"]
        by_ccy.setdefault(ccy, {"closed": 0.0, "open": 0.0})
        by_ccy[ccy]["open"] += r["unrealized_pnl"]
    # totals
    totals = {
        "closed": sum(v["closed"] for v in by_ccy.values()),
        "open":   sum(v["open"]   for v in by_ccy.values()),
        "net":    sum(v["closed"] + v["open"] for v in by_ccy.values()),
    }
    return by_ccy, totals

def _print_pnl_table(by_ccy, totals):
    headers = ["Currency", "Closed PnL", "Open PnL", "Net"]
    widths  = [10,        16,           16,        16]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-" * (sum(widths) + (len(widths)-1)*2))
    for ccy, vals in sorted(by_ccy.items()):
        row = [
            ccy.ljust(widths[0]),
            f'{vals["closed"]:,.6f}'.rjust(widths[1]),
            f'{vals["open"]:,.6f}'.rjust(widths[2]),
            f'{(vals["closed"]+vals["open"]):,.6f}'.rjust(widths[3]),
        ]
        print("  ".join(row))
    print("-" * (sum(widths) + (len(widths)-1)*2))
    print("TOTALS".ljust(widths[0]),
          f'{totals["closed"]:,.6f}'.rjust(widths[1]),
          f'{totals["open"]:,.6f}'.rjust(widths[2]),
          f'{totals["net"]:,.6f}'.rjust(widths[3]), sep="  ")

def cmd_pnl(args):
    ex = _init_bybit_from_env(args.testnet)
    closed_rows = _fetch_closed_pnl_7d(ex)
    open_rows   = _fetch_open_positions_unrealized(ex)
    by_ccy, totals = _group_currency_pnl(closed_rows, open_rows)

    _print_pnl_table(by_ccy, totals)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_days": 7,
        "grouped_pnl_by_currency": by_ccy,
        "totals": totals,
        "closed_rows": closed_rows if args.verbose else None,
        "open_rows": open_rows if args.verbose else None,
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"\nJSON written: {args.out}")

# ====== CLI ======

def main():
    ap = argparse.ArgumentParser(description="Bybit account tools: deposits and currency PnL (7d).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_dep = sub.add_parser("deposits", help="List last-7d deposits (on-chain + BRL proxy) and USD total.")
    ap_dep.add_argument("--out", required=True, help="Path to write JSON output")
    ap_dep.add_argument("--testnet", action="store_true", help="Use Bybit testnet")
    ap_dep.set_defaults(func=cmd_deposits)

    ap_pnl = sub.add_parser("pnl", help="Currency PnL (closed + open) for last 7 days.")
    ap_pnl.add_argument("--out", required=True, help="Path to write JSON output")
    ap_pnl.add_argument("--testnet", action="store_true", help="Use Bybit testnet")
    ap_pnl.add_argument("--verbose", action="store_true", help="Include raw rows in JSON")
    ap_pnl.set_defaults(func=cmd_pnl)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
