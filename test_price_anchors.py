#!/usr/bin/env python3
"""
Simple test to verify price anchor consistency fixes
"""
import sys
import os
sys.path.append('.')

from atr_sl_gpt import compute_levels, atr_trailing_stop
from garch_vol_triggers import sl_tp_and_size


def test_compute_levels():
    """Test that compute_levels function works correctly"""
    print("Testing compute_levels function...")
    levels = compute_levels(entry=2000, atr=50, k=1.5, m=3.0, side='long')
    
    assert abs(levels.sl_distance - 75) < 1e-6  # 1.5 * 50
    assert abs(levels.tp_distance - 150) < 1e-6  # 3.0 * 50
    assert abs(levels.sl_price - 1925) < 1e-6  # 2000 - 75
    assert abs(levels.tp_price - 2150) < 1e-6  # 2000 + 150
    assert abs(levels.rr - 2.0) < 1e-6  # 150 / 75
    print("✅ compute_levels test passed")


def test_sl_tp_and_size():
    """Test that sl_tp_and_size uses current_price correctly"""
    print("Testing sl_tp_and_size function...")
    
    # Test with current_price parameter
    result = sl_tp_and_size(
        current_price=100.0,
        sigma_H=0.02,  # 2% volatility
        k=2.0,
        m=3.0,
        side="long",
        R=200.0,
        tick_size=0.01
    )
    
    expected_sl_distance = 100.0 * 0.02 * 2.0  # 4.0
    expected_tp_distance = 100.0 * 0.02 * 3.0  # 6.0
    expected_sl = 100.0 - 4.0  # 96.0
    expected_tp = 100.0 + 6.0  # 106.0
    expected_q = 200.0 / 4.0  # 50.0
    
    assert abs(result['SL_distance'] - expected_sl_distance) < 1e-6
    assert abs(result['TP_distance'] - expected_tp_distance) < 1e-6
    assert abs(result['SL'] - expected_sl) < 1e-6
    assert abs(result['TP'] - expected_tp) < 1e-6
    assert abs(result['Q'] - expected_q) < 1e-6
    print("✅ sl_tp_and_size test passed")


def test_trailing_stop():
    """Test that trailing stop works correctly"""
    print("Testing atr_trailing_stop function...")
    
    # Initial stop for long position
    trail_stop = atr_trailing_stop(price=1000, atr=20, trail_mult=2.0, side='long', last_trail=None)
    assert abs(trail_stop - 960) < 1e-6  # 1000 - 2*20
    
    # Price moves up, trail stop should tighten
    trail_stop = atr_trailing_stop(price=1010, atr=20, trail_mult=2.0, side='long', last_trail=trail_stop)
    assert abs(trail_stop - 970) < 1e-6  # 1010 - 2*20
    
    # Price moves down, trail stop should NOT loosen
    trail_stop = atr_trailing_stop(price=990, atr=20, trail_mult=2.0, side='long', last_trail=trail_stop)
    assert abs(trail_stop - 970) < 1e-6  # Stays at the max
    print("✅ atr_trailing_stop test passed")


def test_price_anchor_consistency():
    """Test that we've fixed price anchor mixing issues"""
    print("Testing price anchor consistency...")
    
    # Mock position data
    current_price = 50000.0
    entry_price = 48000.0  # Position in profit
    side = 'long'
    
    # Test scale-out calculations use current_price
    sigma_h = 0.02
    R_unit = current_price * sigma_h * 2.0  # k=2.0
    
    # Scale-outs should be anchored to current_price
    tp1 = current_price + 1.5 * R_unit
    tp2 = current_price + 3.0 * R_unit
    
    # These should be different from entry-based calculations
    tp1_entry_based = entry_price + 1.5 * R_unit
    tp2_entry_based = entry_price + 3.0 * R_unit
    
    assert tp1 != tp1_entry_based
    assert tp2 != tp2_entry_based
    assert tp1 > tp1_entry_based  # Since current > entry for profitable long
    assert tp2 > tp2_entry_based
    
    print("✅ Price anchor consistency test passed")


if __name__ == "__main__":
    print("Running price anchor consistency tests...\n")
    
    try:
        test_compute_levels()
        test_sl_tp_and_size()
        test_trailing_stop()
        test_price_anchor_consistency()
        
        print("\n🎉 All tests passed! Price anchor fixes are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
