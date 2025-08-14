# Position Risk Manager Test Suite

This test suite validates the SL/TP shift behavior when `current_price ≠ entry_price`.

## Test Coverage

### Core Functionality Tests (`test_position_risk_manager.py`)

#### 1. SL/TP Shift When Current Price Differs from Entry Price
- **Long Positions**: Tests SL/TP shifting when current > entry and current < entry
- **Short Positions**: Tests SL/TP shifting with proper directional behavior
- **Verification**: 
  - Entry-based percentages remain unchanged across price movements
  - Current-based percentages change appropriately with current price
  - SL/TP absolute levels shift in correct directions

#### 2. Old Entry-Based Percentages Remain Unchanged
- Tests that `sl_pct_entry` and `tp_pct_entry` are constant regardless of current price
- Maintains backward compatibility with existing field names (`sl_pct`, `tp_pct`)
- Verifies dual percentage system works correctly

#### 3. No Regression When Current Price Equals Entry Price
- Tests identical output when `current_price == entry_price`
- Verifies entry-based and current-based percentages are identical in baseline case
- Ensures consistent results across multiple runs

### Integration Tests (`test_position_risk_integration.py`)

#### 1. Multi-Position Analysis
- Tests portfolio-level calculations with different price anchors
- Verifies position-by-position consistency in complex scenarios
- Tests correlation and portfolio risk aggregation

#### 2. Edge Cases
- Extreme price movements (50% gains, 30% losses)
- Zero/minimal volatility scenarios
- Live price fallback mechanisms
- Consistency across different volatility calculation methods

#### 3. Side-Specific Behavior
- Long vs Short position handling
- Proper percentage sign conventions
- Directional correctness for SL/TP placement

## Key Test Scenarios Verified

### ✅ SL/TP Shift Behavior
```python
# Example: Long position with entry at $50,000
entry_price = 50000.0

# Scenario 1: current_price = entry_price
current_price = 50000.0
# SL: $48,500, TP: $53,000
# sl_pct_entry = -3.00%, tp_pct_entry = 6.00%
# sl_pct_current = -3.00%, tp_pct_current = 6.00%

# Scenario 2: current_price > entry_price  
current_price = 52000.0  
# SL: $50,440, TP: $55,120 (both shifted higher)
# sl_pct_entry = 0.88%, tp_pct_entry = 10.24% (CHANGED from entry)
# sl_pct_current = -3.00%, tp_pct_current = 6.00% (UNCHANGED from current)
```

### ✅ Dual Percentage System
- **Entry-based**: `sl_pct_entry`, `tp_pct_entry` - calculated from entry price (historical reference)
- **Current-based**: `sl_pct_current`, `tp_pct_current` - calculated from current price (active risk management)
- **Backward compatibility**: `sl_pct`, `tp_pct` map to entry-based values

### ✅ Price Anchor Consistency
- `anchor_price_used` field indicates 'current' price anchoring
- `entry_price` and `current_price` fields clearly separated
- Scale-out ladders use correct anchors (p1=entry, p2/p3=current)

## Test Data & Mocking

### Mock Components
- **MockPosition**: Simulates position data with entry/current price scenarios
- **MockExchange**: Mocks ccxt exchange interface for funding rates
- **Sample OHLCV Data**: Generates realistic price history for volatility calculations

### Test Parameters
- **Volatility**: 2% sigma_H (realistic crypto volatility)
- **Multipliers**: 1.5x SL, 3.0x TP (conservative professional levels)  
- **Price Scenarios**: ±4% moves from entry (typical intraday movements)

## Running Tests

```bash
# Run specific test
cd /Users/pedrotodescan/market_analysis
python -m pytest tests/test_position_risk_manager.py::TestPositionRiskManagerSLTPShift::test_sl_tp_shift_when_current_price_differs_from_entry_long -v

# Run all tests  
python -m pytest tests/ -v

# Run verification script
python test_verification_corrected.py
```

## Expected Test Results

### ✅ All Tests Should Pass
- SL/TP levels shift correctly with price movements
- Entry-based percentages remain constant (old behavior preserved)  
- Current-based percentages adapt to current price (new behavior)
- No regression when current equals entry price
- Consistent results across multiple runs

### 📊 Sample Output
```
=== Testing SL/TP Shift Behavior ===
Entry Price: $50,000

--- Baseline (current = entry = $50,000) ---
SL: $48,500.00, TP: $53,000.00
SL % from entry: -3.00%, TP % from entry: 6.00%
SL % from current: -3.00%, TP % from current: 6.00%

--- Higher Current Price ($52,000) ---  
SL: $50,440.00 (shift: +$1,940), TP: $55,120.00 (shift: +$2,120)
SL % from entry: 0.88%, TP % from entry: 10.24%
SL % from current: -3.00%, TP % from current: 6.00%

✅ ALL TESTS PASSED! SL/TP shift behavior is working correctly.
```

This test suite ensures the position risk manager correctly handles the transition from entry-price to current-price anchoring while maintaining backward compatibility and providing enhanced risk management capabilities.
