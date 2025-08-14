#!/usr/bin/env python3
"""
Integration tests for Position Risk Manager focusing on edge cases and integration scenarios.

This test suite covers:
- Multi-position analysis with varying price anchors
- Edge cases (extreme price movements, zero volatility, etc.)
- Integration with actual volatility calculation methods
- Portfolio-level risk calculations with price anchor consistency
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import datetime as dt

# Import the classes and functions we need to test
from position_risk_manager import PositionRiskManager
from .test_position_risk_manager import MockPosition, MockExchange, create_sample_ohlcv_data


class TestPositionRiskManagerIntegration:
    """Integration test suite for complex scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_exchange = MockExchange()
        
        # Create multiple positions with different scenarios
        self.positions = [
            MockPosition(  # Winning long position
                symbol='BTC/USDT',
                side='long',
                entryPrice=45000.0,
                size=0.2,
                notional=9000.0,
                leverage=10.0,
                unrealizedPnl=1000.0,
                percentage=11.11,
                liquidationPrice=40500.0,
                initialMargin=900.0
            ),
            MockPosition(  # Losing short position  
                symbol='ETH/USDT',
                side='short',
                entryPrice=2800.0,
                size=2.0,
                notional=5600.0,
                leverage=5.0,
                unrealizedPnl=-400.0,
                percentage=-7.14,
                liquidationPrice=3200.0,
                initialMargin=1120.0
            ),
            MockPosition(  # Breakeven long position
                symbol='SOL/USDT',
                side='long',
                entryPrice=100.0,
                size=20.0,
                notional=2000.0,
                leverage=4.0,
                unrealizedPnl=0.0,
                percentage=0.0,
                liquidationPrice=75.0,
                initialMargin=500.0
            )
        ]
        
        # Create realistic OHLCV data for each symbol
        self.ohlcv_data = {
            'BTC/USDT': create_sample_ohlcv_data(base_price=45000, num_bars=200),
            'ETH/USDT': create_sample_ohlcv_data(base_price=2800, num_bars=200), 
            'SOL/USDT': create_sample_ohlcv_data(base_price=100, num_bars=200)
        }
        
        # Current prices different from entry prices to test anchor behavior
        self.current_prices = {
            'BTC/USDT': 50000.0,  # 11.11% higher than entry (profitable)
            'ETH/USDT': 3000.0,   # 7.14% higher than entry (loss for short)
            'SOL/USDT': 100.0     # Same as entry (breakeven)
        }

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_multi_position_analysis_with_different_anchors(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test multi-position analysis with different current vs entry price scenarios."""
        
        # Setup mocks
        mock_fetch_positions.return_value = self.positions
        mock_market_info.return_value = {'tick_size': 0.01}
        
        def mock_klines_side_effect(exchange, symbol, *args, **kwargs):
            return self.ohlcv_data[symbol]
        
        def mock_live_price_side_effect(exchange, symbol):
            return self.current_prices[symbol]
        
        mock_klines.side_effect = mock_klines_side_effect
        mock_live_price.side_effect = mock_live_price_side_effect
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            # Analyze all positions
            result = manager.analyze_all_positions()
        
        # Verify each position has consistent anchor behavior
        for position in self.positions:
            symbol = position.symbol
            analysis = result['positions'][symbol]
            
            entry_price = position.entryPrice
            current_price = self.current_prices[symbol]
            
            # Verify prices are captured correctly
            assert analysis['entry_price'] == entry_price
            assert analysis['current_price'] == current_price
            assert analysis['anchor_price_used'] == 'current'
            
            # Entry-based percentages should be calculated from entry price
            sl_pct_entry_manual = ((analysis['stop_loss'] - entry_price) / entry_price) * 100
            tp_pct_entry_manual = ((analysis['take_profit'] - entry_price) / entry_price) * 100
            
            if position.side == 'short':
                sl_pct_entry_manual = ((entry_price - analysis['stop_loss']) / entry_price) * 100
                tp_pct_entry_manual = ((entry_price - analysis['take_profit']) / entry_price) * 100
            
            assert np.isclose(analysis['sl_pct_entry'], sl_pct_entry_manual, rtol=1e-6)
            assert np.isclose(analysis['tp_pct_entry'], tp_pct_entry_manual, rtol=1e-6)
            
            # Current-based percentages should be calculated from current price
            if position.side == 'long':
                sl_pct_current_manual = ((analysis['stop_loss'] - current_price) / current_price) * 100
                tp_pct_current_manual = ((analysis['take_profit'] - current_price) / current_price) * 100
            else:
                sl_pct_current_manual = ((analysis['stop_loss'] - current_price) / current_price) * 100
                tp_pct_current_manual = ((analysis['take_profit'] - current_price) / current_price) * 100
                
            assert np.isclose(analysis['sl_pct_current'], sl_pct_current_manual, rtol=1e-6)
            assert np.isclose(analysis['tp_pct_current'], tp_pct_current_manual, rtol=1e-6)
        
        # Portfolio metrics should aggregate correctly
        portfolio = result['portfolio']
        assert portfolio['total_positions'] == 3
        assert 'total_risk_if_all_sl_hit' in portfolio
        assert 'total_reward_if_all_tp_hit' in portfolio

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_extreme_price_movement_scenarios(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test behavior with extreme price movements (large gaps between entry and current)."""
        
        # Create position with extreme scenarios
        extreme_position = MockPosition(
            symbol='EXTREME/USDT',
            side='long',
            entryPrice=1000.0,
            size=1.0,
            notional=1000.0,
            leverage=20.0,
            unrealizedPnl=0.0,
            percentage=0.0,
            liquidationPrice=950.0,
            initialMargin=50.0
        )
        
        mock_fetch_positions.return_value = [extreme_position]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = create_sample_ohlcv_data(base_price=1000, num_bars=100)
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            # Test extreme upward movement (50% gain)
            mock_live_price.return_value = 1500.0
            analysis_up = manager.analyze_position_volatility(extreme_position)
            
            # Test extreme downward movement (30% loss)
            mock_live_price.return_value = 700.0
            analysis_down = manager.analyze_position_volatility(extreme_position)
            
            # Test normal case
            mock_live_price.return_value = 1000.0
            analysis_normal = manager.analyze_position_volatility(extreme_position)
        
        # Entry-based percentages should remain constant across all scenarios
        assert analysis_up['sl_pct_entry'] == analysis_down['sl_pct_entry']
        assert analysis_up['sl_pct_entry'] == analysis_normal['sl_pct_entry']
        assert analysis_up['tp_pct_entry'] == analysis_down['tp_pct_entry'] 
        assert analysis_up['tp_pct_entry'] == analysis_normal['tp_pct_entry']
        
        # Current-based percentages should vary significantly
        assert abs(analysis_up['sl_pct_current'] - analysis_down['sl_pct_current']) > 10
        assert abs(analysis_up['tp_pct_current'] - analysis_down['tp_pct_current']) > 10
        
        # SL/TP levels should shift appropriately
        assert analysis_up['stop_loss'] > analysis_normal['stop_loss'] > analysis_down['stop_loss']
        assert analysis_up['take_profit'] > analysis_normal['take_profit'] > analysis_down['take_profit']
        
        # Liquidation safety checks should reflect current price
        if analysis_down.get('liquidation_buffer_safe') is not None:
            # When price drops significantly, liquidation risk should increase
            assert not analysis_down['liquidation_buffer_safe']

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit') 
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_zero_or_minimal_volatility_edge_case(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test behavior with zero or minimal volatility scenarios."""
        
        # Create flat price data (minimal volatility)
        flat_data = create_sample_ohlcv_data(base_price=1000, num_bars=100)
        # Make prices very stable
        flat_data['close'] = 1000.0 + np.random.normal(0, 0.01, len(flat_data))  # 0.01 std dev
        flat_data['high'] = flat_data['close'] + 0.05
        flat_data['low'] = flat_data['close'] - 0.05
        flat_data['open'] = flat_data['close']
        
        mock_fetch_positions.return_value = [self.positions[0]]  # Use first position
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = flat_data
        mock_live_price.return_value = 1005.0  # Slightly different from flat price
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            analysis = manager.analyze_position_volatility(self.positions[0])
        
        # Should still produce valid results even with minimal volatility
        assert 'stop_loss' in analysis
        assert 'take_profit' in analysis
        assert analysis['stop_loss'] > 0
        assert analysis['take_profit'] > 0
        
        # ATR should be very small but non-zero
        assert analysis.get('atr', 0) >= 0
        assert analysis.get('atr_pct', 0) >= 0
        
        # Risk calculations should still work
        assert analysis.get('dollar_risk', 0) > 0
        assert analysis.get('dollar_reward', 0) > 0

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_consistency_across_multiple_runs(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that results are consistent across multiple analysis runs."""
        
        mock_fetch_positions.return_value = [self.positions[0]]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = self.ohlcv_data['BTC/USDT']
        mock_live_price.return_value = 52000.0  # Fixed current price
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            # Run analysis multiple times
            results = []
            for _ in range(5):
                analysis = manager.analyze_position_volatility(self.positions[0])
                results.append(analysis)
        
        # All critical fields should be identical across runs
        critical_fields = [
            'entry_price', 'current_price', 'stop_loss', 'take_profit',
            'sl_pct_entry', 'tp_pct_entry', 'sl_pct_current', 'tp_pct_current',
            'anchor_price_used', 'dollar_risk', 'dollar_reward'
        ]
        
        for field in critical_fields:
            values = [r.get(field) for r in results if field in r]
            if values:
                # All values should be identical (or very close for floating point)
                for i in range(1, len(values)):
                    if isinstance(values[0], (int, float)):
                        assert np.isclose(values[0], values[i], rtol=1e-12), \
                            f"Field {field} inconsistent across runs: {values[0]} vs {values[i]}"
                    else:
                        assert values[0] == values[i], \
                            f"Field {field} inconsistent across runs: {values[0]} vs {values[i]}"

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_volatility_method_impact_on_anchor_consistency(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that different volatility calculation methods don't affect anchor consistency."""
        
        mock_fetch_positions.return_value = [self.positions[0]]
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_live_price.return_value = 51000.0
        
        # Test with different data lengths to trigger different volatility methods
        short_data = create_sample_ohlcv_data(base_price=45000, num_bars=50)  # May not have enough for GARCH
        long_data = create_sample_ohlcv_data(base_price=45000, num_bars=600)   # Should have enough for all methods
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            # Test with short data (likely to use HAR or ATR only)
            mock_klines.return_value = short_data
            analysis_short = manager.analyze_position_volatility(self.positions[0])
            
            # Test with long data (likely to use GARCH + HAR blend)
            mock_klines.return_value = long_data
            analysis_long = manager.analyze_position_volatility(self.positions[0])
        
        # Regardless of volatility method, anchor behavior should be consistent
        assert analysis_short['anchor_price_used'] == analysis_long['anchor_price_used'] == 'current'
        assert analysis_short['entry_price'] == analysis_long['entry_price']
        assert analysis_short['current_price'] == analysis_long['current_price']
        
        # Entry-based percentages should be similar (may vary slightly due to different volatilities)
        assert abs(analysis_short['sl_pct_entry'] - analysis_long['sl_pct_entry']) < 5.0  # Allow 5% difference
        assert abs(analysis_short['tp_pct_entry'] - analysis_long['tp_pct_entry']) < 5.0
        
        # Current-based percentages should also be similar
        assert abs(analysis_short['sl_pct_current'] - analysis_long['sl_pct_current']) < 5.0
        assert abs(analysis_short['tp_pct_current'] - analysis_long['tp_pct_current']) < 5.0

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_side_specific_behavior_consistency(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that long and short positions behave consistently with price anchors."""
        
        # Create matching long and short positions
        long_pos = MockPosition(
            symbol='TEST/USDT', side='long', entryPrice=1000.0, size=1.0,
            notional=1000.0, leverage=10.0
        )
        
        short_pos = MockPosition(
            symbol='TEST/USDT', side='short', entryPrice=1000.0, size=1.0,
            notional=1000.0, leverage=10.0
        )
        
        mock_market_info.return_value = {'tick_size': 0.01}
        mock_klines.return_value = create_sample_ohlcv_data(base_price=1000, num_bars=100)
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            # Test with current price above entry (favorable for long, unfavorable for short)
            mock_live_price.return_value = 1100.0
            mock_fetch_positions.return_value = [long_pos]
            long_analysis = manager.analyze_position_volatility(long_pos)
            
            mock_fetch_positions.return_value = [short_pos]
            short_analysis = manager.analyze_position_volatility(short_pos)
        
        # Both should use current price anchor
        assert long_analysis['anchor_price_used'] == 'current'
        assert short_analysis['anchor_price_used'] == 'current'
        
        # Both should have same entry and current prices
        assert long_analysis['entry_price'] == short_analysis['entry_price'] == 1000.0
        assert long_analysis['current_price'] == short_analysis['current_price'] == 1100.0
        
        # For long positions with current > entry:
        # - SL should be below current price (negative %)
        # - TP should be above current price (positive %)
        assert long_analysis['sl_pct_current'] < 0
        assert long_analysis['tp_pct_current'] > 0
        
        # For short positions with current > entry:
        # - SL should be above current price (positive %)  
        # - TP should be below current price (negative %)
        assert short_analysis['sl_pct_current'] > 0
        assert short_analysis['tp_pct_current'] < 0

    @patch('position_risk_manager.get_klines_bybit')
    @patch('position_risk_manager.get_live_price_bybit')
    @patch('position_risk_manager.get_bybit_market_info')
    @patch('position_risk_manager.fetch_bybit_positions')
    def test_portfolio_correlation_with_different_anchors(
        self, mock_fetch_positions, mock_market_info, mock_live_price, mock_klines
    ):
        """Test that portfolio-level calculations work correctly with different price anchors."""
        
        mock_fetch_positions.return_value = self.positions[:2]  # Use first two positions
        mock_market_info.return_value = {'tick_size': 0.01}
        
        def mock_klines_side_effect(exchange, symbol, *args, **kwargs):
            return self.ohlcv_data[symbol]
        
        def mock_live_price_side_effect(exchange, symbol):
            return self.current_prices[symbol]
        
        mock_klines.side_effect = mock_klines_side_effect
        mock_live_price.side_effect = mock_live_price_side_effect
        
        with patch.dict('os.environ', {'BYBIT_API_KEY': 'test', 'BYBIT_API_SECRET': 'test'}):
            manager = PositionRiskManager(sandbox=True)
            manager.exchange = self.mock_exchange
            
            result = manager.analyze_all_positions()
        
        portfolio = result['portfolio']
        
        # Portfolio metrics should be calculated correctly
        assert portfolio['total_positions'] == 2
        assert 'total_risk_if_all_sl_hit' in portfolio
        assert 'total_reward_if_all_tp_hit' in portfolio
        assert portfolio['total_risk_if_all_sl_hit'] > 0
        assert portfolio['total_reward_if_all_tp_hit'] > 0
        
        # Portfolio risk/reward should be reasonable ratio
        portfolio_rr = portfolio.get('portfolio_risk_reward_ratio', 0)
        assert portfolio_rr > 0  # Should be positive
        
        # Sum of individual dollar risks should equal total portfolio risk
        individual_risks = []
        for pos in self.positions[:2]:
            analysis = result['positions'][pos.symbol]
            individual_risks.append(analysis['dollar_risk'])
        
        expected_total_risk = sum(individual_risks)
        assert np.isclose(portfolio['total_risk_if_all_sl_hit'], expected_total_risk, rtol=1e-6)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
