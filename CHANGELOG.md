# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Current-Price Anchoring & Dual Reporting Enhancement

- **Current-Price Anchoring**: Enhanced SL/TP calculations to use live market prices instead of historical entry prices
  - `sl_tp_and_size()` now defaults to current market price for more accurate risk management
  - Provides real-time accuracy in volatile markets by reducing lag from stale entry prices
  - Maintains backward compatibility with `entry_price` parameter

- **Dual Percentage Reporting**: Added comprehensive dual reporting system for risk metrics
  - **Entry-based metrics**: `sl_pct_entry`, `tp_pct_entry` (backward compatibility)
  - **Current-based metrics**: `sl_pct_current`, `tp_pct_current` (enhanced accuracy)
  - `anchor_price_used` field indicates which price reference was used for calculations

- **Enhanced Position Analysis**:
  - `analyze_position_volatility()` now implements current-price anchoring by default
  - Live price fetching integrated into position risk assessment
  - Dual reporting enables comparison between entry-based and current-based risk metrics
  - Improved accuracy for active position management in fast-moving markets

- **Risk Management Improvements**:
  - Current price used for scale-out ladder calculations (except breakeven level)
  - Trailing stop suggestions anchored to current price for better responsiveness
  - Liquidation buffer analysis enhanced with current-price reference points
  - Position sizing calculations updated to reflect current market conditions

### Enhanced

- **Volatility Forecasting**: Improved blended volatility calculations using current price anchoring
- **Risk Assessment**: More accurate dollar risk/reward calculations based on live market conditions
- **Report Generation**: Added current vs entry-based percentage comparisons in risk reports
- **Error Handling**: Enhanced fallback mechanisms when live price fetching fails

### Technical Details

- Functions updated: `sl_tp_and_size()`, `analyze_position_volatility()`
- New output keys: `sl_pct_current`, `tp_pct_current`, `anchor_price_used`
- Backward compatibility: Existing `sl_pct`, `tp_pct` keys maintained as entry-based aliases
- Live price integration: Automatic fallback to last close price if live price unavailable

### Notes

This enhancement addresses the lag issue in traditional entry-price based risk management, particularly important in highly volatile cryptocurrency markets where entry prices may quickly become outdated reference points for risk assessment.

## [Previous Versions]

*Historical changelog entries would go here for previous releases*
