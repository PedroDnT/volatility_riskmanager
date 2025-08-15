import pytest
import numpy as np
from market_analysis.atr_sl_gpt import (
    compute_levels,
    position_size_usdt,
    atr_trailing_stop,
)

def test_compute_levels_long():
    """Test SL/TP level calculation for a long position."""
    levels = compute_levels(entry=2000, atr=50, k=1.5, m=3.0, side='long')

    assert np.isclose(levels.sl_distance, 75)  # 1.5 * 50
    assert np.isclose(levels.tp_distance, 150) # 3.0 * 50
    assert np.isclose(levels.sl_price, 1925)   # 2000 - 75
    assert np.isclose(levels.tp_price, 2150)   # 2000 + 150
    assert np.isclose(levels.rr, 2.0)         # 150 / 75

def test_compute_levels_short():
    """Test SL/TP level calculation for a short position."""
    levels = compute_levels(entry=300, atr=10, k=2.0, m=4.0, side='short')

    assert np.isclose(levels.sl_distance, 20) # 2.0 * 10
    assert np.isclose(levels.tp_distance, 40) # 4.0 * 10
    assert np.isclose(levels.sl_price, 320)   # 300 + 20
    assert np.isclose(levels.tp_price, 260)   # 300 - 40
    assert np.isclose(levels.rr, 2.0)        # 40 / 20

def test_position_size_usdt():
    """Test position sizing calculation."""
    qty = position_size_usdt(account_risk=100.0, sl_distance=25.0)
    assert np.isclose(qty, 4.0) # 100 / 25

def test_position_size_usdt_zero_distance():
    """Test that position sizing raises an error for zero SL distance."""
    with pytest.raises(ValueError):
        position_size_usdt(account_risk=100.0, sl_distance=0)

def test_atr_trailing_stop_long():
    """Test ATR trailing stop logic for a long position."""
    # Initial stop
    trail_stop = atr_trailing_stop(price=1000, atr=20, trail_mult=2.0, side='long', last_trail=None)
    assert np.isclose(trail_stop, 960) # 1000 - 2*20

    # Price moves up, trail stop should tighten
    trail_stop = atr_trailing_stop(price=1010, atr=20, trail_mult=2.0, side='long', last_trail=trail_stop)
    assert np.isclose(trail_stop, 970) # 1010 - 2*20

    # Price moves down, trail stop should NOT loosen
    trail_stop = atr_trailing_stop(price=990, atr=20, trail_mult=2.0, side='long', last_trail=trail_stop)
    assert np.isclose(trail_stop, 970) # Stays at the max

def test_atr_trailing_stop_short():
    """Test ATR trailing stop logic for a short position."""
    # Initial stop
    trail_stop = atr_trailing_stop(price=500, atr=10, trail_mult=3.0, side='short', last_trail=None)
    assert np.isclose(trail_stop, 530) # 500 + 3*10

    # Price moves down, trail stop should tighten
    trail_stop = atr_trailing_stop(price=490, atr=10, trail_mult=3.0, side='short', last_trail=trail_stop)
    assert np.isclose(trail_stop, 520) # 490 + 3*10

    # Price moves up, trail stop should NOT loosen
    trail_stop = atr_trailing_stop(price=510, atr=10, trail_mult=3.0, side='short', last_trail=trail_stop)
    assert np.isclose(trail_stop, 520) # Stays at the min
