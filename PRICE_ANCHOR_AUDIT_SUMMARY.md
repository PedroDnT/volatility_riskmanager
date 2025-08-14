# Price Anchor Audit Summary

## Task Completed: Step 7 - Safeguard dependent calculations

### Overview
Audited subsequent code sections (scale-outs, trailing stop, liquidation buffer, oversize ratio) to confirm they now use `current_price` where appropriate or remain entry-based by design. Fixed math that incorrectly mixed the two anchors.

### Issues Found and Fixed

#### 1. Scale-out Ladder (Lines 484-510)
**Issue:** Scale-out levels (tp1, tp2) were incorrectly anchored to `entry_price` instead of `current_price`
```python
# BEFORE (incorrect mixing)
tp1 = entry_price + scale_r1 * R_unit  # R_unit calculated from current_price
tp2 = entry_price + scale_r2 * R_unit  # but anchored to entry_price
```

**Fix:** Changed to use `current_price` for consistency with SL/TP calculations
```python
# AFTER (consistent current_price anchor)
tp1 = current_price + scale_r1 * R_unit  # Both R_unit and anchor use current_price
tp2 = current_price + scale_r2 * R_unit
```

#### 2. Reduce-only Ladder (Lines 497-510)
**Issue:** Mixed anchoring - some levels used entry, others used current
**Fix:** Clarified design intent with comments:
- `ladder_p1 = entry_price` - Intentionally entry-based (breakeven level by design)
- `ladder_p2 = current_price + 0.5 * R_unit` - Current-price based
- `ladder_p3 = tp1` - Current-price based (inherits from tp1)

#### 3. Trailing Stop Calculation (Lines 512-517)
**Issue:** Used `live_price` instead of `current_price` for consistency
```python
# BEFORE (inconsistent variable usage)
r_unreal = max(0.0, (live_price - entry_price) / R_unit)
trail_suggestion = compute_trailing_stop(entry=live_price, ...)
```

**Fix:** Use `current_price` throughout for consistency
```python
# AFTER (consistent current_price usage)
r_unreal = max(0.0, (current_price - entry_price) / R_unit)
trail_suggestion = compute_trailing_stop(entry=current_price, ...)
```

#### 4. Liquidation Buffer Calculation (Lines 519-536)
**Issue:** Buffer ratio calculation mixed entry_price with current SL (calculated from current_price)
```python
# BEFORE (incorrect mixing)
sl_to_liq_distance = abs(risk_params['SL'] - liquidation_price)  # SL from current_price
sl_to_entry_distance = abs(entry_price - risk_params['SL'])      # but ratio uses entry_price
```

**Fix:** Use consistent `current_price` anchor
```python
# AFTER (consistent current_price anchor)
sl_to_liq_distance = abs(risk_params['SL'] - liquidation_price)
sl_to_current_distance = abs(current_price - risk_params['SL'])  # Use current_price
```

### Design Decisions Confirmed

#### Appropriately Entry-based by Design:
1. **Time-stop counters** - Count bars below/above entry (lines 182-203) ✅
2. **Reduce-only ladder p1** - Breakeven level at entry_price ✅
3. **Percentage calculations from entry** - For backward compatibility (sl_pct, tp_pct) ✅

#### Appropriately Current-price Based:
1. **Main SL/TP calculation** - Uses `current_price` via `sl_tp_and_size()` ✅
2. **Scale-out levels** - Now consistently use `current_price` ✅
3. **Trailing stop** - Now uses `current_price` ✅
4. **Liquidation buffer ratio** - Now uses `current_price` ✅
5. **Dollar risk/reward calculations** - Use R_unit_current from current_price ✅

#### Oversize Ratio (Lines 541-543):
**Verified:** Correctly uses optimal_position_size (calculated from current_price) vs current_position_size ✅

### Testing
Created and ran comprehensive tests (`test_price_anchors.py`) to verify:
- Basic function correctness
- Price anchor consistency 
- No incorrect mixing of anchors

**Result:** ✅ All tests passed

### Impact
- **Consistency:** All calculations now use appropriate and consistent price anchors
- **Accuracy:** Scale-outs and liquidation buffers now calculated correctly relative to current market conditions
- **Clarity:** Added comments explaining design intent for mixed-anchor scenarios
- **Backward Compatibility:** Maintained dual metrics for entry-based percentages

### Files Modified
1. `position_risk_manager.py` - Fixed scale-outs, trailing stop, and liquidation buffer calculations
2. `test_price_anchors.py` - Created verification tests

This audit ensures mathematical consistency and eliminates the risk of incorrect risk management decisions due to anchor mixing.
