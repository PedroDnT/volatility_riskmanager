# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a modular cryptocurrency volatility analysis and risk management toolkit that uses advanced statistical models to forecast volatility and calculate dynamic stop-loss/take-profit levels. The project consists of four specialized Python scripts:

1. `get_position.py` - Fetches current derivatives positions from Bybit with detailed PnL and exposure data
2. `garch_vol_triggers.py` - Advanced volatility analysis using GARCH and HAR-RV models with dynamic SL/TP calculation
3. `atr_sl_gpt.py` - ATR-based stop-loss/take-profit calculations with trailing stops for crypto perpetuals
4. `position_risk_manager.py` - Comprehensive risk management system that combines position data with volatility analysis

## Dependencies

The project requires the following Python packages:
- `ccxt>=4.3.95` - for cryptocurrency exchange data and API integration
- `pandas>=2.2.2` - for data manipulation and time series analysis
- `numpy>=1.26.4` - for numerical computations
- `python-dotenv>=1.0.0` - for environment variable management
- `arch>=5.0.0` - for GARCH volatility modeling

Install dependencies with:
```bash
pip install -r requirements.txt
```

## Environment Variables

The scripts use environment variables for API credentials via a `.env` file:
- `BYBIT_API_KEY` - Required for fetching Bybit derivatives positions and authenticated data
- `BYBIT_API_SECRET` - Required for Bybit API authentication

Create a `.env` file in the project directory:
```bash
BYBIT_API_KEY=your_bybit_api_key_here
BYBIT_API_SECRET=your_bybit_api_secret_here
```

Note: API credentials are optional for market data fetching but required for position data and trading operations.

## Running the Application

Execute individual scripts based on your needs:

**Fetch current positions:**
```bash
python get_position.py
```

**Comprehensive risk management for all positions:**
```bash
python position_risk_manager.py
```

**Volatility analysis for specific symbols:**
```bash
python garch_vol_triggers.py
```

**ATR-based SL/TP with command-line options:**
```bash
python atr_sl_gpt.py --exchange bybit --symbol ETH/USDT:USDT --timeframe 4h \
    --entry 2400 --side long --account-risk 100 --leverage 5
```

## Architecture Notes

- **Modular design**: Specialized scripts for positions, volatility analysis, and risk management
- **Advanced volatility modeling**: GARCH(1,1) and HAR-RV forecasting methods
- **Systematic risk management**: Automated SL/TP calculation based on volatility and leverage
- **Multiple exchanges**: Built on ccxt library for broad exchange support
- **Defensive programming**: Handles missing dependencies and API keys gracefully
- **No trading execution**: This is analysis-only; no actual trades are placed
- **Error handling**: Individual symbol/model failures don't crash the entire process

## Code Structure

### get_position.py
- `fetch_bybit_positions()` - Fetches current derivatives positions with PnL and exposure details
- `main()` - Displays formatted position data and JSON output

### garch_vol_triggers.py
- `get_klines_bybit()` - Fetches OHLCV data from Bybit via ccxt
- `get_live_price_bybit()` - Gets real-time price for a symbol
- `compute_atr()` - Calculates Average True Range for volatility measurement
- `har_rv_nowcast()` - HAR-RV volatility forecasting using realized variance
- `garch_sigma_ann_and_sigma_H()` - GARCH(1,1) volatility modeling and forecasting
- `sl_tp_and_size()` - Dynamic stop-loss/take-profit calculation based on volatility forecasts
- `analyze_multiple_symbols_bybit()` - Multi-symbol analysis with various strategies

### atr_sl_gpt.py
- `atr_wilder()` - Wilder's ATR calculation using exponential smoothing
- `compute_levels()` - ATR-based SL/TP level calculations
- `atr_trailing_stop()` - Bar-close trailing stop implementation
- `position_size_usdt()` - Position sizing for USDT-margined contracts
- `approx_liq_price()` - Liquidation price estimation with safety buffers

### position_risk_manager.py
- `PositionRiskManager` - Main class for comprehensive risk analysis
- `fetch_positions()` - Retrieves all open positions
- `analyze_position_volatility()` - Analyzes volatility for each position
- `generate_report()` - Creates detailed risk management report
- `export_to_json()` - Exports analysis results to JSON

## Volatility Models

### GARCH(1,1)
Generalized Autoregressive Conditional Heteroskedasticity model that captures volatility clustering in financial time series. Uses the `arch` package for robust parameter estimation.

### HAR-RV (Heterogeneous Autoregressive Realized Volatility)
A simpler but effective model that uses daily, weekly, and monthly realized variance components to forecast future volatility. More stable for shorter time series.

## Risk Management Features

- **Dynamic SL/TP**: Stop-loss and take-profit levels scaled by volatility forecasts
- **Leverage-adjusted parameters**: Tighter stops for high-leverage positions
- **Position sizing**: Risk-based position sizing using volatility-adjusted stop distances
- **Liquidation buffers**: Safety checks to ensure adequate distance between stops and liquidation
- **Multiple strategies**: Trend-following vs mean-reversion parameter sets
- **Portfolio-wide metrics**: Total risk exposure and reward potential across all positions
- **Health monitoring**: Position status classification (CRITICAL, WARNING, NORMAL, PROFITABLE)

## Usage Example

For systematic risk management of all open positions:

```bash
# Run the position risk manager
python position_risk_manager.py
```

This will:
1. Fetch all open positions from Bybit
2. Analyze historical volatility for each symbol
3. Calculate optimal SL/TP levels based on:
   - Current volatility (ATR, GARCH, HAR-RV)
   - Position leverage
   - Liquidation price buffers
4. Generate a comprehensive report with:
   - Individual position recommendations
   - Portfolio-wide risk metrics
   - Action items for positions at risk
5. Export results to `risk_analysis.json`