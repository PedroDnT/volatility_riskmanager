#!/usr/bin/env python3
"""
ATR-based SL/TP and trailing stop utilities for crypto perpetuals (Bybit/Binance/etc) via CCXT.

Key features:
- Fetch OHLCV via CCXT
- Compute ATR (Wilder) and ATR ratio filter
- Systematic SL/TP sizing: SL = k * ATR, TP = m * ATR
- ATR trailing stop (bar-close update)
- Position sizing for USDT-margined linear contracts
- Optional (commented) example placing orders on Bybit via CCXT

Usage example (dry run):
    python atr_sl_tp.py --exchange bybit --symbol ETH/USDT:USDT --timeframe 4h --atr 20 --k 1.4 --m 2.8 \
        --entry 2400 --side long --account-risk 100 --leverage 5 --trail-mult 1.2

Notes:
- You'll need valid API keys set via environment variables or ccxt config if you enable trading.
- Internet is required when fetching OHLCV live.
"""
from __future__ import annotations
import argparse
import math
from dataclasses import dataclass
from typing import Optional, Tuple, List
import json
import ccxt
import pandas as pd
import numpy as np

# ---------- Core calculations ----------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def atr_wilder(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """
    Wilder's ATR using RMA (exponential smoothing with alpha=1/n).
    df columns expected: ['timestamp','open','high','low','close','volume']
    """
    tr = true_range(df['high'], df['low'], df['close'])
    atr = tr.ewm(alpha=1.0/n, adjust=False).mean()
    return atr

@dataclass
class Levels:
    sl_price: float
    tp_price: float
    sl_distance: float
    tp_distance: float
    rr: float

def compute_levels(entry: float, atr: float, k: float, m: float, side: str) -> Levels:
    sl_dist = k * atr
    tp_dist = m * atr
    if side.lower() == 'long':
        sl = entry - sl_dist
        tp = entry + tp_dist
    elif side.lower() == 'short':
        sl = entry + sl_dist
        tp = entry - tp_dist
    else:
        raise ValueError("side must be 'long' or 'short'")
    rr = tp_dist / sl_dist if sl_dist > 0 else float('inf')
    return Levels(sl_price=sl, tp_price=tp, sl_distance=sl_dist, tp_distance=tp_dist, rr=rr)

def atr_trailing_stop(price: float, atr: float, trail_mult: float, side: str, last_trail: Optional[float]) -> float:
    """
    Bar-close trailing stop: place stop at (price - trail_mult*atr) for long, (price + ...) for short.
    Never loosen the stop (only tighten). Return the new stop.
    """
    if side.lower() == 'long':
        proposed = price - trail_mult * atr
        if last_trail is None:
            return proposed
        return max(last_trail, proposed)  # tighten only
    else:
        proposed = price + trail_mult * atr
        if last_trail is None:
            return proposed
        return min(last_trail, proposed)

def position_size_usdt(account_risk: float, sl_distance: float) -> float:
    """
    For linear USDT-margined contracts, PnL ≈ qty * (price_change).
    If SL distance is denominated in the same price units, the USDT risk ≈ qty * sl_distance.
    Solve qty = account_risk / sl_distance.
    """
    if sl_distance <= 0:
        raise ValueError("SL distance must be > 0")
    return account_risk / sl_distance

def approx_liq_price(entry: float, side: str, leverage: float, maint_margin_frac: float = 0.005) -> float:
    """
    Very rough liquidation price estimate ignoring fees/funding and exchange-specific nuances.
    This is conservative. Always check exchange calc.
    """
    if leverage <= 0:
        return float('nan')
    if side.lower() == 'long':
        # naive: liquidation when unrealized loss ≈ initial margin + maintenance
        # price move fraction ≈ (1/leverage) - maint_margin_frac
        frac = (1.0 / leverage) - maint_margin_frac
        frac = max(frac, 0.001)
        return entry * (1.0 - frac)
    else:
        frac = (1.0 / leverage) - maint_margin_frac
        frac = max(frac, 0.001)
        return entry * (1.0 + frac)

def check_liq_buffer(entry: float, sl: float, liq: float, side: str) -> float:
    """Return buffer ratio = distance(liq)/distance(SL) (should be >= 2 ideally)."""
    if side.lower() == 'long':
        sl_dist = abs(entry - sl)
        liq_dist = abs(entry - liq)
    else:
        sl_dist = abs(entry - sl)
        liq_dist = abs(liq - entry)
    if sl_dist == 0:
        return float('inf')
    return liq_dist / sl_dist

# ---------- CCXT helpers ----------

def load_exchange(name: str, sandbox: bool = False) -> ccxt.Exchange:
    ex_class = getattr(ccxt, name)
    exchange = ex_class({
        "enableRateLimit": True,
        # API keys can be provided via environment variables:
        # 'apiKey': os.getenv('API_KEY'),
        # 'secret': os.getenv('API_SECRET'),
    })
    if sandbox and hasattr(exchange, 'set_sandbox_mode'):
        exchange.set_sandbox_mode(True)
    return exchange

def fetch_ohlcv_df(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# ---------- CLI ----------

