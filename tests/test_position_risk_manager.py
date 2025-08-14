#!/usr/bin/env python3
"""
Test suite for Position Risk Manager SL/TP calculation behavior.

This test suite verifies:
1. SL/TP shift when current_price ≠ entry_price
2. Old entry-based percentages remain unchanged  
3. No regression when current_price == entry_price (identical output)

The tests use mocked position and price feed data to isolate the logic.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import Dict, Any, Optional
import datetime as dt

# Import the classes and functions we need to test
from position_risk_manager import PositionRiskManager
from garch_vol_triggers import sl_tp_and_size


@dataclass
class MockPosition:
    """Mock position data structure for testing."""
    symbol: str
    side: str
    entryPrice: float
    size: float
    notional: float
    leverage: float
    unrealizedPnl: float = 0.0
    percentage: float = 0.0
    liquidationPrice: Optional[float] = None
    initialMargin: Optional[float] = None

    def __getitem__(self, key):
        return getattr(self, key)
    
    def get(self, key, default=None):
        return getattr(self, key, default)


class MockExchange:
    """Mock ccxt exchange for testing."""
    
    def __init__(self):
        self.markets = {}
        self.funding_rates = {}
    
    def fetch_funding_rate(self, symbol):
        return {'fundingRate': self.funding_rates.get(symbol, 0.0001)}
    
    def fetch_funding_rates(self, symbols):
        return {sym: {'fundingRate': self.funding_rates.get(sym, 0.0001)} for sym in symbols}


def create_sample_ohlcv_data(base_price: float = 50000, num_bars: int = 100) -> pd.DataFrame:
    """Create sample OHLCV data for testing with realistic price movements."""
    np.random.seed(42)  # For reproducible tests
    
    timestamps = pd.date_range(
        start=dt.datetime.now() - dt.timedelta(days=num_bars//6), 
        periods=num_bars, 
        freq='4H'
    )
    
    # Generate realistic price series with some volatility
    returns = np.random.normal(0, 0.01, num_bars)  # 1% volatility
    prices = [base_price]
    
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    # Create OHLCV from close prices with realistic spreads
    data = []
    for i, (ts, close) in enumerate(zip(timestamps, prices)):
        spread = close * 0.001  # 0.1% spread
        high = close + spread * np.random.uniform(0.5, 2.0)
        low = close - spread * np.random.uniform(0.5, 2.0)
        open_price = prices[i-1] if i > 0 else close
        volume = np.random.uniform(1000, 5000)
        
        data.append({
            'timestamp': ts,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df


class TestPositionRiskManagerSLTPShift:
    """Test suite for SL/TP shift behavior in PositionRiskManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_exchange = MockExchange()
        
        # Create mock position data
        self.long_position = MockPosition(
            symbol='BTC/USDT',
            side='long',
            entryPrice=50000.0,
            size=0.1,
            notional=5000.0,
            leverage=10.0,
            unrealizedPnl=0.0,
            percentage=0.0,
            liquidationPrice=45000.0,
            initialMargin=500.0
        )
        
        self.short_position = MockPosition(
            symbol='ETH/USDT',
            side='short',
            entryPrice=3000.0,
            size=1.0,
            notional=3000.0,
            leverage=5.0,
            unrealizedPnl=0.0,
            percentage=0.0,
            liquidationPrice=3500.0,
            initialMargin=600.0
        )
        
        # Mock OHLCV data
        self.btc_ohlcv = create_sample_ohlcv_data(base_price=50000, num_bars=100)
        self.eth_ohlcv = create_sample_ohlcv_data(base_price=3000, num_bars=100)
    
    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_sl_tp_shift_when_current_price_differs_from_entry_long(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that SL/TP levels shift when current_price ≠ entry_price for LONG positions."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        
        # Test case 1: current_price = entry_price (baseline)
        mock_live_price.return_value = 50000.0  # Same as entry
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            baseline_analysis = manager.analyze_position_volatility(self.long_position)
        
        # Test case 2: current_price > entry_price
        mock_live_price.return_value = 52000.0  # 4% higher than entry
        
        higher_price_analysis = manager.analyze_position_volatility(self.long_position)
        
        # Test case 3: current_price < entry_price  
        mock_live_price.return_value = 48000.0  # 4% lower than entry
        
        lower_price_analysis = manager.analyze_position_volatility(self.long_position)
        
        # Verify SL/TP shift behavior
        entry_price = 50000.0
        
        # Entry-based percentages should remain unchanged across all scenarios
        assert baseline_analysis['sl_pct_entry'] == higher_price_analysis['sl_pct_entry']
        assert baseline_analysis['sl_pct_entry'] == lower_price_analysis['sl_pct_entry']
        assert baseline_analysis['tp_pct_entry'] == higher_price_analysis['tp_pct_entry']
        assert baseline_analysis['tp_pct_entry'] == lower_price_analysis['tp_pct_entry']
        
        # Current-based percentages should differ when current_price changes
        assert baseline_analysis['sl_pct_current'] != higher_price_analysis['sl_pct_current']
        assert baseline_analysis['sl_pct_current'] != lower_price_analysis['sl_pct_current']
        assert baseline_analysis['tp_pct_current'] != higher_price_analysis['tp_pct_current']
        assert baseline_analysis['tp_pct_current'] != lower_price_analysis['tp_pct_current']
        
        # For long positions, when current > entry, SL/TP should be higher than baseline
        assert higher_price_analysis['stop_loss'] > baseline_analysis['stop_loss']
        assert higher_price_analysis['take_profit'] > baseline_analysis['take_profit']
        
        # For long positions, when current < entry, SL/TP should be lower than baseline
        assert lower_price_analysis['stop_loss'] < baseline_analysis['stop_loss']
        assert lower_price_analysis['take_profit'] < baseline_analysis['take_profit']
        
        # Verify anchor price is correctly used
        assert baseline_analysis['anchor_price_used'] == 'current'
        assert higher_price_analysis['anchor_price_used'] == 'current'
        assert lower_price_analysis['anchor_price_used'] == 'current'
        
        # Verify current_price is correctly captured
        assert baseline_analysis['current_price'] == 50000.0
        assert higher_price_analysis['current_price'] == 52000.0
        assert lower_price_analysis['current_price'] == 48000.0
        
        # Entry price should remain constant
        assert baseline_analysis['entry_price'] == entry_price
        assert higher_price_analysis['entry_price'] == entry_price
        assert lower_price_analysis['entry_price'] == entry_price

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_sl_tp_shift_when_current_price_differs_from_entry_short(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that SL/TP levels shift when current_price ≠ entry_price for SHORT positions."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.short_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.eth_ohlcv
        
        # Test case 1: current_price = entry_price (baseline)
        mock_live_price.return_value = 3000.0  # Same as entry
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            baseline_analysis = manager.analyze_position_volatility(self.short_position)
        
        # Test case 2: current_price < entry_price (favorable for short)
        mock_live_price.return_value = 2800.0  # Lower than entry
        
        lower_price_analysis = manager.analyze_position_volatility(self.short_position)
        
        # Test case 3: current_price > entry_price (unfavorable for short)
        mock_live_price.return_value = 3200.0  # Higher than entry
        
        higher_price_analysis = manager.analyze_position_volatility(self.short_position)
        
        # Verify SL/TP shift behavior
        entry_price = 3000.0
        
        # Entry-based percentages should remain unchanged across all scenarios
        assert baseline_analysis['sl_pct_entry'] == lower_price_analysis['sl_pct_entry']
        assert baseline_analysis['sl_pct_entry'] == higher_price_analysis['sl_pct_entry']
        assert baseline_analysis['tp_pct_entry'] == lower_price_analysis['tp_pct_entry']
        assert baseline_analysis['tp_pct_entry'] == higher_price_analysis['tp_pct_entry']
        
        # Current-based percentages should differ when current_price changes
        assert baseline_analysis['sl_pct_current'] != lower_price_analysis['sl_pct_current']
        assert baseline_analysis['sl_pct_current'] != higher_price_analysis['sl_pct_current']
        assert baseline_analysis['tp_pct_current'] != lower_price_analysis['tp_pct_current']
        assert baseline_analysis['tp_pct_current'] != higher_price_analysis['tp_pct_current']
        
        # For short positions, when current < entry, SL/TP should be lower than baseline
        assert lower_price_analysis['stop_loss'] < baseline_analysis['stop_loss']
        assert lower_price_analysis['take_profit'] < baseline_analysis['take_profit']
        
        # For short positions, when current > entry, SL/TP should be higher than baseline
        assert higher_price_analysis['stop_loss'] > baseline_analysis['stop_loss'] 
        assert higher_price_analysis['take_profit'] > baseline_analysis['take_profit']
        
        # Verify current_price is correctly captured
        assert baseline_analysis['current_price'] == 3000.0
        assert lower_price_analysis['current_price'] == 2800.0
        assert higher_price_analysis['current_price'] == 3200.0

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_no_regression_when_current_equals_entry(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test no regression when current_price == entry_price (identical output)."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        mock_live_price.return_value = 50000.0  # Same as entry
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            # Run analysis twice to check for consistency
            analysis_1 = manager.analyze_position_volatility(self.long_position)
            analysis_2 = manager.analyze_position_volatility(self.long_position)
        
        # When current_price == entry_price, entry-based and current-based percentages should be identical
        assert analysis_1['sl_pct_entry'] == analysis_1['sl_pct_current']
        assert analysis_1['tp_pct_entry'] == analysis_1['tp_pct_current']
        
        # Results should be identical across multiple runs
        critical_fields = [
            'stop_loss', 'take_profit', 'sl_pct_entry', 'tp_pct_entry', 
            'sl_pct_current', 'tp_pct_current', 'dollar_risk', 'dollar_reward',
            'optimal_position_size', 'risk_reward_ratio'
        ]
        
        for field in critical_fields:
            if field in analysis_1 and field in analysis_2:
                assert np.isclose(analysis_1[field], analysis_2[field], rtol=1e-10), \
                    f"Field {field} differs between runs: {analysis_1[field]} vs {analysis_2[field]}"

    @patch('position_risk_manager.get_klines_bybit') 
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_scale_out_ladder_uses_correct_anchor(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that scale-out ladder uses correct price anchors."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        mock_live_price.return_value = 52000.0  # Different from entry
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            analysis = manager.analyze_position_volatility(self.long_position)
        
        entry_price = 50000.0
        current_price = 52000.0
        
        # Verify reduce-only ladder anchors
        ladder = analysis['reduce_only_ladder']
        
        # p1 should be entry-based (breakeven level by design)
        assert ladder['p1_price'] == entry_price
        
        # p2 and p3 should be current-price based
        assert ladder['p2_price'] != entry_price  # Should be based on current price
        assert ladder['p3_price'] != entry_price  # Should be based on current price
        
        # tp1 and tp2 should also be current-price based
        assert analysis['tp1'] > current_price  # For long position
        assert analysis['tp2'] > current_price  # For long position

    def test_sl_tp_and_size_function_direct(self):
        """Test the sl_tp_and_size function directly with different price scenarios."""
        
        # Test parameters
        sigma_H = 0.02  # 2% volatility
        k = 1.5  # SL multiplier
        m = 3.0  # TP multiplier
        R = 100.0  # Risk amount
        
        # Scenario 1: Using current_price parameter (new behavior)
        result_current = sl_tp_and_size(
            price=50000.0, 
            sigma_H=sigma_H, 
            k=k, 
            m=m, 
            side='long', 
            R=R
        )
        
        # Scenario 2: Using entry_price parameter (backward compatibility)
        result_entry = sl_tp_and_size(
            entry_price=50000.0,
            sigma_H=sigma_H,
            k=k,
            m=m,
            side='long',
            R=R
        )
        
        # Scenario 3: Using current_price kwarg (backward compatibility)
        result_current_kwarg = sl_tp_and_size(
            current_price=50000.0,
            sigma_H=sigma_H,
            k=k,
            m=m,
            side='long',
            R=R
        )
        
        # All should produce identical results when the price is the same
        assert result_current['SL'] == result_entry['SL']
        assert result_current['TP'] == result_entry['TP']
        assert result_current['SL'] == result_current_kwarg['SL']
        assert result_current['TP'] == result_current_kwarg['TP']
        
        # Test with different prices to ensure the function uses the right anchor
        result_different = sl_tp_and_size(
            price=52000.0,  # Different price
            sigma_H=sigma_H,
            k=k,
            m=m,
            side='long',
            R=R
        )
        
        # Results should differ when price is different
        assert result_current['SL'] != result_different['SL']
        assert result_current['TP'] != result_different['TP']
        
        # For long position with higher price, SL and TP should be higher
        assert result_different['SL'] > result_current['SL']
        assert result_different['TP'] > result_current['TP']

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit') 
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_percentage_calculation_accuracy(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test accuracy of percentage calculations for both entry-based and current-based."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        mock_live_price.return_value = 51000.0  # 2% higher than entry
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            analysis = manager.analyze_position_volatility(self.long_position)
        
        entry_price = 50000.0
        current_price = 51000.0
        sl_price = analysis['stop_loss']
        tp_price = analysis['take_profit']
        
        # Manual calculation of entry-based percentages for long position
        expected_sl_pct_entry = ((sl_price - entry_price) / entry_price) * 100
        expected_tp_pct_entry = ((tp_price - entry_price) / entry_price) * 100
        
        # Manual calculation of current-based percentages for long position
        expected_sl_pct_current = ((sl_price - current_price) / current_price) * 100
        expected_tp_pct_current = ((tp_price - current_price) / current_price) * 100
        
        # Verify calculations match
        assert np.isclose(analysis['sl_pct_entry'], expected_sl_pct_entry, rtol=1e-6)
        assert np.isclose(analysis['tp_pct_entry'], expected_tp_pct_entry, rtol=1e-6)
        assert np.isclose(analysis['sl_pct_current'], expected_sl_pct_current, rtol=1e-6)
        assert np.isclose(analysis['tp_pct_current'], expected_tp_pct_current, rtol=1e-6)
        
        # For long positions, SL should be negative percentage from both entry and current
        assert analysis['sl_pct_entry'] < 0
        assert analysis['sl_pct_current'] < 0
        
        # For long positions, TP should be positive percentage from both entry and current
        assert analysis['tp_pct_entry'] > 0
        assert analysis['tp_pct_current'] > 0

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_dollar_risk_reward_with_different_anchors(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that dollar risk/reward calculations use current price anchor correctly."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        
        # Test with current_price higher than entry
        mock_live_price.return_value = 52000.0
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            analysis = manager.analyze_position_volatility(self.long_position)
        
        current_price = 52000.0
        sl_price = analysis['stop_loss']
        tp_price = analysis['take_profit']
        position_size = analysis['position_size']
        optimal_size = analysis['optimal_position_size']
        
        # Calculate expected dollar risk/reward based on current price
        expected_r_unit_current = abs(sl_price - current_price)
        expected_optimal_dollar_risk = optimal_size * expected_r_unit_current
        expected_optimal_dollar_reward = optimal_size * (tp_price - current_price)
        expected_current_dollar_risk = position_size * expected_r_unit_current
        expected_current_dollar_reward = position_size * (tp_price - current_price)
        
        # Verify calculations use current_price anchor
        assert np.isclose(analysis['dollar_risk'], expected_optimal_dollar_risk, rtol=1e-6)
        assert np.isclose(analysis['dollar_reward'], expected_optimal_dollar_reward, rtol=1e-6)
        assert np.isclose(analysis['current_dollar_risk'], expected_current_dollar_risk, rtol=1e-6)
        assert np.isclose(analysis['current_dollar_reward'], expected_current_dollar_reward, rtol=1e-6)

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info') 
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_live_price_fallback_mechanism(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that the system falls back to last close price when live price is unavailable."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        mock_live_price.return_value = None  # Live price unavailable
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            analysis = manager.analyze_position_volatility(self.long_position)
        
        # Should use the last close price from OHLCV data
        expected_current_price = float(self.btc_ohlcv['close'].iloc[-1])
        assert np.isclose(analysis['current_price'], expected_current_price, rtol=1e-6)

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_backward_compatibility_fields(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that backward compatibility fields are maintained."""
        
        # Setup mocks
        mock_fetch_positions.return_value = [self.long_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.btc_ohlcv
        mock_live_price.return_value = 51000.0
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            analysis = manager.analyze_position_volatility(self.long_position)
        
        # Old field names should still exist and match their entry-based counterparts
        assert 'sl_pct' in analysis
        assert 'tp_pct' in analysis
        assert analysis['sl_pct'] == analysis['sl_pct_entry']
        assert analysis['tp_pct'] == analysis['tp_pct_entry']
        
        # New field names should also exist  
        assert 'sl_pct_current' in analysis
        assert 'tp_pct_current' in analysis
        assert 'sl_pct_entry' in analysis
        assert 'tp_pct_entry' in analysis
        
        # Anchor information should be present
        assert analysis['anchor_price_used'] == 'current'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
