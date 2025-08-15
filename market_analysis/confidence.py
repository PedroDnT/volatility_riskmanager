import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Any


def calculate_confidence_score(
    df: pd.DataFrame, side: str, volatility_metrics: Dict[str, Any]
) -> Tuple[int, List[str]]:
    """
    Calculates a confidence score for a trading position based on multiple factors.

    Args:
        df: DataFrame with OHLCV data.
        side: 'long' or 'short'.
        volatility_metrics: Dictionary containing volatility analysis results.

    Returns:
        A tuple containing the confidence score and a list of contributing factors.
    """
    score = 0
    confidence_factors = []

    try:
        close = df["close"]

        # 1. Trend strength (EMA crossover)
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        if side == "long" and ema20.iloc[-1] > ema50.iloc[-1]:
            score += 1
            confidence_factors.append("Uptrend (EMA20 > EMA50)")
        elif side == "short" and ema20.iloc[-1] < ema50.iloc[-1]:
            score += 1
            confidence_factors.append("Downtrend (EMA20 < EMA50)")

        # 2. Breakout confirmation (Donchian channels)
        donch_high = df["high"].rolling(window=20, min_periods=20).max()
        donch_low = df["low"].rolling(window=20, min_periods=20).min()
        if side == "long" and close.iloc[-1] > donch_high.iloc[-2]:
            score += 1
            confidence_factors.append("Breakout above Donchian high")
        elif side == "short" and close.iloc[-1] < donch_low.iloc[-2]:
            score += 1
            confidence_factors.append("Breakout below Donchian low")

        # 3. Volatility regime analysis
        rets = np.log(close).diff()
        vol_20 = rets.rolling(window=20).std()
        vol_100 = rets.rolling(window=100).std()
        current_vol = float(vol_20.iloc[-1])
        avg_vol = float(vol_100.median())

        if current_vol < avg_vol * 0.8:
            score += 1
            confidence_factors.append("Low volatility regime")
        elif current_vol > avg_vol * 1.5:
            score -= 1
            confidence_factors.append("High volatility regime")

        # 4. Price momentum (RSI proxy)
        rsi_period = 14
        gains = close.diff().where(close.diff() > 0, 0)
        losses = -close.diff().where(close.diff() < 0, 0)
        avg_gain = gains.rolling(window=rsi_period).mean()
        avg_loss = losses.rolling(window=rsi_period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        if side == "long" and rsi.iloc[-1] > 50:
            score += 1
            confidence_factors.append("Positive momentum (RSI > 50)")
        elif side == "short" and rsi.iloc[-1] < 50:
            score += 1
            confidence_factors.append("Negative momentum (RSI < 50)")

        # 5. Volatility stability (GARCH validation)
        garch_sigma = volatility_metrics.get("garch_sigma_ann")
        har_sigma = volatility_metrics.get("har_sigma_ann")
        if garch_sigma and har_sigma:
            garch_har_ratio = garch_sigma / har_sigma
            if 0.5 <= garch_har_ratio <= 2.0:
                score += 1
                confidence_factors.append("Volatility models aligned")
            elif garch_har_ratio > 3.0:
                score -= 1
                confidence_factors.append("Volatility models disagree")

    except Exception as e:
        print(f"  Confidence scoring error: {e}")

    # Clamp score to a reasonable range
    score = max(-2, min(5, score))
    return score, confidence_factors
