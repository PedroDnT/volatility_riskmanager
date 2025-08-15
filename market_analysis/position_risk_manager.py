#!/usr/bin/env python3
"""
Position Risk Manager
--------------------
Combines position fetching with volatility analysis to provide 
systematic risk management recommendations for all open positions.

This script:
1. Fetches current open positions from Bybit
2. Analyzes volatility for each position's symbol
3. Calculates optimal SL/TP levels based on volatility and leverage
4. Generates comprehensive risk management report
"""

import os
import json
import math
import datetime as dt
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
import ccxt
from dotenv import load_dotenv

# Import position fetching functionality
from .get_position import fetch_bybit_positions
from .config import settings

# Import volatility analysis functions
from .garch_vol_triggers import (
    get_klines_bybit,
    get_live_price_bybit,
    get_bybit_market_info,
    compute_atr,
    sigma_ann_and_sigma_H_from_har,
    garch_sigma_ann_and_sigma_H,
    sl_tp_and_size,
    blended_sigma_h,
    validate_garch_result,
    compute_trailing_stop
)
from .utils import _hours_per_bar
from .confidence import calculate_confidence_score
from .reporting import generate_report, _calculate_portfolio_metrics


class PositionRiskManager:
    """Manages risk analysis for all open positions."""
    
    def __init__(self, sandbox: bool = False):
        """Initialize the risk manager.
        
        Args:
            sandbox: If True, use Bybit testnet
        """
        self.sandbox = sandbox
        self.positions = []
        self.risk_analysis = {}
        self.cfg = settings
        
        # Centralized exchange object creation
        load_dotenv()
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env file")

        self.exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': self.sandbox,
            'options': {
                'defaultType': 'linear',
            }
        })

    def fetch_positions(self) -> List[Dict[str, Any]]:
        """Fetch current open positions."""
        print("=" * 80)
        print("Fetching current open positions...")
        print("=" * 80)
        
        self.positions = fetch_bybit_positions(self.exchange)
        
        if not self.positions:
            print("No open positions found.")
            return []
            
        print(f"Found {len(self.positions)} open position(s)")
        return self.positions
    
    def analyze_position_volatility(self, position: Dict[str, Any], 
                                   timeframe: str = "4h", 
                                   lookback_days: int = 30) -> Dict[str, Any]:
        """Analyze volatility for a single position.
        
        Args:
            position: Position data dictionary
            timeframe: Timeframe for volatility analysis
            lookback_days: Days of historical data to analyze
            
        Returns:
            Dictionary with volatility metrics and recommended SL/TP levels
        """
        symbol = position['symbol']
        side = position['side'].lower()
        entry_price = position['entryPrice']
        leverage = position.get('leverage', 10.0)
        
        print(f"\nAnalyzing {symbol}...")
        
        # Get market info for tick size
        market_info = get_bybit_market_info(self.exchange, symbol)
        tick_size = market_info['tick_size'] if market_info else 0.00001
        
        # Fetch historical data
        try:
            df = get_klines_bybit(
                self.exchange,
                symbol=symbol,
                timeframe=timeframe,
                since=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
            )
            
            if df.empty:
                print(f"  Warning: No historical data for {symbol}")
                return self._get_default_risk_params(position)
                
            # Ensure enough bars for GARCH; if not, extend lookback and refetch just for GARCH fit
            bar_hours = _hours_per_bar(timeframe)
            required_days = int(math.ceil((500 * bar_hours) / 24.0) + 5)
            if len(np.log(df["close"]).diff().dropna()) < 500 and lookback_days < required_days:
                try:
                    df_garch = get_klines_bybit(
                        self.exchange,
                        symbol=symbol,
                        timeframe=timeframe,
                        since=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=required_days)
                    )
                    if not df_garch.empty:
                        df = df_garch
                except Exception:
                    pass
                
        except Exception as e:
            print(f"  Error fetching data for {symbol}: {e}")
            return self._get_default_risk_params(position)
        
        # Calculate ATR
        df["ATR20"] = compute_atr(df, period=20)
        atr = float(df["ATR20"].iloc[-1])
        atr_pct = (atr / entry_price) * 100
        
        # Get current live price
        live_price = get_live_price_bybit(self.exchange, symbol)
        if live_price is None:
            live_price = float(df["close"].iloc[-1])
        
        # Calculate volatility using multiple methods
        volatility_metrics: Dict[str, Optional[float]] = {}
        H_hours = int(self.cfg.get('vol', {}).get('horizon_hours', 4))
        
        # HAR-RV volatility
        try:
            sigma_ann_har, sigma_H_har = sigma_ann_and_sigma_H_from_har(
                df["close"], interval=timeframe, horizon_hours=H_hours
            )
            volatility_metrics['har_sigma_ann'] = sigma_ann_har
            volatility_metrics['har_sigma_H'] = sigma_H_har
        except Exception as e:
            print(f"  HAR-RV failed: {e}")
            volatility_metrics['har_sigma_ann'] = None
            volatility_metrics['har_sigma_H'] = None
        
        # GARCH volatility with validation
        garch_ok = True
        try:
            sigma_ann_garch, sigma_H_garch, garch_res = garch_sigma_ann_and_sigma_H(
                df["close"], interval=timeframe, horizon_hours=H_hours
            )
            rets = np.log(df["close"]).diff().dropna().values
            issues = validate_garch_result(rets, garch_res, sigma_ann_garch, H_hours)
            if issues:
                garch_ok = False
                print("  GARCH checks:", "; ".join(issues))
            volatility_metrics['garch_sigma_ann'] = sigma_ann_garch if garch_ok else None
            volatility_metrics['garch_sigma_H'] = sigma_H_garch if garch_ok else None
        except Exception as e:
            print(f"  GARCH failed: {e}")
            volatility_metrics['garch_sigma_ann'] = None
            volatility_metrics['garch_sigma_H'] = None
        
        # Blend vols in absolute horizon units
        sigmaH_blend_abs = blended_sigma_h(
            volatility_metrics.get('garch_sigma_ann'),
            volatility_metrics.get('har_sigma_ann'),
            atr_abs=atr,
            price=entry_price,
            cfg=self.cfg
        )
        primary_sigma_frac = sigmaH_blend_abs / entry_price
        vol_method = "VOL_BLEND"
        
        # Enhanced confidence scoring with volatility analysis
        score, confidence_factors = calculate_confidence_score(df, side, volatility_metrics)
        
        # Enhanced dynamic risk management (2-3% based on confidence/volatility)
        risk_cfg = self.cfg.get('risk', {})
        base_pct = float(risk_cfg.get('base_target_pct', 0.025))  # 2.5% base
        min_p   = float(risk_cfg.get('min_target_pct', 0.02))     # 2% minimum
        max_p   = float(risk_cfg.get('max_target_pct', 0.03))     # 3% maximum
        use_dyn = bool(risk_cfg.get('use_dynamic', True))
        
        # Professional risk scaling based on confidence score
        if use_dyn:
            if score >= 4:  # High confidence
                risk_mult = 1.2  # 3% risk
            elif score >= 2:  # Medium confidence
                risk_mult = 1.0  # 2.5% risk
            elif score >= 0:  # Low confidence
                risk_mult = 0.9  # 2.25% risk
            else:  # Negative confidence
                risk_mult = 0.8  # 2% risk
        else:
            risk_mult = 1.0
        
        risk_target_pct = base_pct * risk_mult
        risk_target_pct = float(np.clip(risk_target_pct, min_p, max_p))
        
        # Professional stop-loss and take-profit levels (2-4× ATR)
        stops_cfg = self.cfg.get('stops', {})
        
        # Base multipliers by leverage (professional standards)
        if leverage >= 20:
            k_sl_base = float(stops_cfg.get('k_sl_lev20', 1.5))  # Increased from 1.0
            m_tp_base = float(stops_cfg.get('m_tp_lev20', 3.0))  # Increased from 2.6
        elif leverage >= 15:
            k_sl_base = float(stops_cfg.get('k_sl_lev15', 1.8))  # Increased from 1.2
            m_tp_base = float(stops_cfg.get('m_tp_lev15', 3.5))  # Increased from 3.0
        elif leverage >= 10:
            k_sl_base = float(stops_cfg.get('k_sl_lev10', 2.2))  # Increased from 1.5
            m_tp_base = float(stops_cfg.get('m_tp_lev10', 4.0))  # Increased from 3.5
        else:
            k_sl_base = float(stops_cfg.get('k_sl_low', 2.5))    # Increased from 1.8
            m_tp_base = float(stops_cfg.get('m_tp_low', 4.5))    # Increased from 4.0
        
        # Volatility-based adjustments
        atr_pct = (atr / entry_price) * 100
        vol_adjustment = 1.0
        
        # Adjust for extreme volatility (wider stops in high vol)
        if atr_pct > 5.0:  # Very high volatility
            vol_adjustment = 1.3
        elif atr_pct > 3.0:  # High volatility
            vol_adjustment = 1.15
        elif atr_pct < 1.0:  # Low volatility
            vol_adjustment = 0.9
        
        # Confidence-based adjustments
        confidence_adjustment = 1.0 + (score * 0.05)  # ±25% based on confidence
        
        # Apply adjustments
        k_sl_eff = k_sl_base * vol_adjustment * confidence_adjustment
        m_tp_eff = m_tp_base * vol_adjustment * confidence_adjustment
        
        # Ensure minimum professional standards
        k_sl_eff = max(k_sl_eff, 1.5)  # Minimum 1.5× ATR for stops
        m_tp_eff = max(m_tp_eff, 2.5)  # Minimum 2.5× ATR for targets
        
        # Calculate SL/TP levels with optimal position sizing
        target_risk_dollars = position['notional'] * risk_target_pct
        risk_params = sl_tp_and_size(
            entry_price=entry_price,
            sigma_H=primary_sigma_frac,
            k=k_sl_eff,
            m=m_tp_eff,
            side=side,
            R=target_risk_dollars,
            tick_size=tick_size
        )
        
        # Scale-out ladder
        scale_r1 = float(stops_cfg.get('scaleout_r1', 1.5))
        scale_r2 = float(stops_cfg.get('scaleout_r2', 3.0))
        frac1 = float(stops_cfg.get('scaleout_frac1', 0.4))
        frac2 = float(stops_cfg.get('scaleout_frac2', 0.3))
        frac_runner = float(stops_cfg.get('leave_runner_frac', 0.3))
        R_unit = risk_params['SL_distance']
        if side == 'long':
            tp1 = entry_price + scale_r1 * R_unit
            tp2 = entry_price + scale_r2 * R_unit
        else:
            tp1 = entry_price - scale_r1 * R_unit
            tp2 = entry_price - scale_r2 * R_unit
        
        # Trailing stop suggestion (assume unrealized R from current price)
        if side == 'long':
            r_unreal = max(0.0, (live_price - entry_price) / R_unit) if R_unit > 0 else 0.0
        else:
            r_unreal = max(0.0, (entry_price - live_price) / R_unit) if R_unit > 0 else 0.0
        trail_suggestion = compute_trailing_stop(entry=live_price, direction=side, atr=atr, cfg=self.cfg, r_unrealized=r_unreal)
        
        # Check liquidation buffer if liquidation price exists
        liquidation_price = position.get('liquidationPrice')
        liq_buffer_safe = True
        liq_buffer_ratio = None
        
        if liquidation_price:
            if side == 'long':
                sl_to_liq_distance = abs(risk_params['SL'] - liquidation_price)
                sl_to_entry_distance = abs(entry_price - risk_params['SL'])
                if sl_to_entry_distance > 0:
                    liq_buffer_ratio = sl_to_liq_distance / sl_to_entry_distance
                    liq_buffer_safe = risk_params['SL'] > liquidation_price * 1.1
            else:  # short
                sl_to_liq_distance = abs(liquidation_price - risk_params['SL'])
                sl_to_entry_distance = abs(risk_params['SL'] - entry_price)
                if sl_to_entry_distance > 0:
                    liq_buffer_ratio = sl_to_liq_distance / sl_to_entry_distance
                    liq_buffer_safe = risk_params['SL'] < liquidation_price * 0.9
        
        # Calculate dollar risk and reward using OPTIMAL position size
        optimal_position_size = risk_params['Q']
        current_position_size = position['size']
        
        if side == 'long':
            optimal_dollar_risk = optimal_position_size * (entry_price - risk_params['SL'])
            optimal_dollar_reward = optimal_position_size * (risk_params['TP'] - entry_price)
            sl_pct = ((risk_params['SL'] - entry_price) / entry_price) * 100
            tp_pct = ((risk_params['TP'] - entry_price) / entry_price) * 100
        else:
            optimal_dollar_risk = optimal_position_size * (risk_params['SL'] - entry_price)
            optimal_dollar_reward = optimal_position_size * (entry_price - risk_params['TP'])
            sl_pct = ((entry_price - risk_params['SL']) / entry_price) * 100
            tp_pct = ((entry_price - risk_params['TP']) / entry_price) * 100
        
        # Risk/Reward for current position size
        if side == 'long':
            current_dollar_risk = current_position_size * (entry_price - risk_params['SL'])
            current_dollar_reward = current_position_size * (risk_params['TP'] - entry_price)
        else:
            current_dollar_risk = current_position_size * (risk_params['SL'] - entry_price)
            current_dollar_reward = current_position_size * (entry_price - risk_params['TP'])
        
        dollar_risk = optimal_dollar_risk
        dollar_reward = optimal_dollar_reward
        rr_ratio = dollar_reward / dollar_risk if dollar_risk > 0 else 0
        
        return {
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'current_price': live_price,
            'position_size': current_position_size,
            'optimal_position_size': optimal_position_size,
            'notional': position['notional'],
            'leverage': leverage,
            'current_pnl': position.get('unrealizedPnl', 0),
            'current_pnl_pct': position.get('percentage', 0),
            'liquidation_price': liquidation_price,
            
            # Volatility metrics
            'atr': atr,
            'atr_pct': atr_pct,
            'volatility_method': vol_method,
            'sigma_H': primary_sigma_frac,
            'har_sigma_ann': volatility_metrics.get('har_sigma_ann'),
            'garch_sigma_ann': volatility_metrics.get('garch_sigma_ann'),
            'sigmaH_blend_abs': sigmaH_blend_abs,
            
            # Risk management levels
            'stop_loss': risk_params['SL'],
            'take_profit': risk_params['TP'],
            'sl_distance': risk_params['SL_distance'],
            'tp_distance': risk_params['TP_distance'],
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'k_multiplier': k_sl_eff,
            'm_multiplier': m_tp_eff,
            
            # Scale-outs
            'tp1': tp1,
            'tp2': tp2,
            'scaleout_frac1': frac1,
            'scaleout_frac2': frac2,
            'leave_runner_frac': frac_runner,
            'trail_stop_suggestion': trail_suggestion,
            'regime_score': score,
            'confidence_factors': confidence_factors,
            'risk_target_pct': risk_target_pct,
            'volatility_adjustment': vol_adjustment,
            'confidence_adjustment': confidence_adjustment,
            
            # Risk metrics
            'dollar_risk': dollar_risk,
            'dollar_reward': dollar_reward,
            'current_dollar_risk': current_dollar_risk,
            'current_dollar_reward': current_dollar_reward,
            'risk_reward_ratio': rr_ratio,
            'liquidation_buffer_safe': liq_buffer_safe,
            'liquidation_buffer_ratio': liq_buffer_ratio,
        }
    
    def _get_default_risk_params(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """Get default risk parameters when volatility analysis fails."""
        entry_price = position['entryPrice']
        side = position['side'].lower()
        leverage = position.get('leverage', 10.0)
        
        # Conservative default: 2% stop loss, 4% take profit
        if side == 'long':
            sl = entry_price * 0.98
            tp = entry_price * 1.04
        else:
            sl = entry_price * 1.02
            tp = entry_price * 0.96
        
        return {
            'symbol': position['symbol'],
            'side': side,
            'entry_price': entry_price,
            'stop_loss': sl,
            'take_profit': tp,
            'volatility_method': 'DEFAULT',
            'position_health': 'UNKNOWN',
            'action_required': 'Manual review required',
            'error': 'Volatility analysis failed - using default parameters'
        }
    
    def analyze_all_positions(self) -> Dict[str, Any]:
        """Analyze all open positions and generate risk metrics."""
        if not self.positions:
            self.fetch_positions()
        
        if not self.positions:
            return {}
        
        print("\n" + "=" * 80)
        print("ANALYZING POSITION RISKS")
        print("=" * 80)
        
        for position in self.positions:
            analysis = self.analyze_position_volatility(position)
            self.risk_analysis[position['symbol']] = analysis
        
        # Calculate portfolio-wide metrics and correlation caps
        portfolio_metrics = self._calculate_portfolio_metrics()
        self.risk_analysis['portfolio'] = portfolio_metrics
        self._apply_portfolio_correlation_cap()
        
        return {
            'positions': self.risk_analysis,
            'portfolio': portfolio_metrics
        }
    
    def _calculate_portfolio_metrics(self) -> Dict[str, Any]:
        """Calculate portfolio-wide risk metrics."""
        return _calculate_portfolio_metrics(self.positions, self.risk_analysis)

    def _apply_portfolio_correlation_cap(self) -> None:
        """Compute correlation clusters and cap cluster risk as per settings."""
        if not self.positions:
            return
        port_cfg = self.cfg.get('portfolio', {})
        lookback_days = int(port_cfg.get('corr_lookback_days', 60))
        corr_threshold = float(port_cfg.get('corr_threshold', 0.7))
        cluster_cap = float(port_cfg.get('cluster_risk_cap_pct', 0.5))

        # Build returns matrix on 4h timeframe
        symbol_to_returns: Dict[str, pd.Series] = {}
        for pos in self.positions:
            sym = pos['symbol']
            try:
                df = get_klines_bybit(self.exchange, sym, timeframe='4h', since=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days))
                if not df.empty:
                    symbol_to_returns[sym] = np.log(df['close']).diff().dropna()
            except Exception:
                continue
        if len(symbol_to_returns) < 2:
            return
        rets_df = pd.DataFrame(symbol_to_returns).dropna(how='any')
        if rets_df.empty:
            return
        corr = rets_df.corr()

        # Simple clustering: union-find via threshold
        symbols = list(symbol_to_returns.keys())
        clusters: List[List[str]] = []
        visited = set()
        for s in symbols:
            if s in visited:
                continue
            cluster = [s]
            visited.add(s)
            for t in symbols:
                if t in visited:
                    continue
                if abs(float(corr.loc[s, t])) >= corr_threshold:
                    cluster.append(t)
                    visited.add(t)
            clusters.append(cluster)

        # Compute total risk budget (sum of proposed risk dollars)
        total_risk_dollars = sum(self.risk_analysis[s]['dollar_risk'] for s in self.risk_analysis if isinstance(self.risk_analysis.get(s), dict) and 'dollar_risk' in self.risk_analysis[s])
        if total_risk_dollars <= 0:
            return

        # Cap cluster risk and scale down each member proportionally
        for cluster in clusters:
            cluster_risk = sum(self.risk_analysis.get(sym, {}).get('dollar_risk', 0.0) for sym in cluster)
            max_cluster_risk = cluster_cap * total_risk_dollars
            if cluster_risk > max_cluster_risk and cluster_risk > 0:
                scale = max_cluster_risk / cluster_risk
                for sym in cluster:
                    analysis = self.risk_analysis.get(sym)
                    if not analysis:
                        continue
                    # scale optimal size and resulting dollar risk/reward
                    analysis['optimal_position_size'] *= scale
                    analysis['dollar_risk'] *= scale
                    analysis['dollar_reward'] *= scale
                    analysis['portfolio_note'] = f"Cluster {cluster} risk capped {cluster_risk:.2f}→{max_cluster_risk:.2f} (ρ≥{corr_threshold})"
 
    def generate_report(self) -> str:
        """Generate comprehensive risk management report."""
        return generate_report(self.risk_analysis, self.positions, self.cfg)
    
    def export_to_json(self, filename: str = "risk_analysis.json"):
        """Export risk analysis to JSON file."""
        output = {
            'timestamp': dt.datetime.now(dt.timezone.utc).isoformat(),
            'positions': self.risk_analysis,
            'portfolio': self._calculate_portfolio_metrics() if self.risk_analysis else {}
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"\nRisk analysis exported to {filename}")

