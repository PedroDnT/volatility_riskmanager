"""
bybit_positions.py
------------------

This script fetches open derivatives positions from Bybit using the `ccxt` library.
It requires BYBIT_API_KEY and BYBIT_API_SECRET to be set in a .env file.

Example usage::

    python main.py

The program will fetch and display all open positions with their details including
symbol, side, size, entry price, mark price, and unrealized PnL.

Note: This script only reads position data and does not execute any trades.
"""

import os
import json
from typing import Dict, List, Any

try:
    import ccxt  # type: ignore
except ImportError as exc:
    raise ImportError(
        "ccxt library is required. Install it via 'pip install ccxt'."
    ) from exc

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError as exc:
    raise ImportError(
        "python-dotenv library is required. Install it via 'pip install python-dotenv'."
    ) from exc


def fetch_bybit_positions(exchange: ccxt.Exchange) -> List[Dict[str, Any]]:
    """Fetch current derivatives positions from Bybit.

    Returns a list of position dictionaries, or an empty list if
    API credentials are missing or there's an error.
    """
    try:
        # Fetch positions
        positions = exchange.fetch_positions()

        # Filter to only open positions
        open_positions = []
        for pos in positions:
            if pos['contracts'] and pos['contracts'] > 0:
                # Calculate percentage manually if not available
                percentage = pos.get('percentage')
                if percentage is None and pos.get('unrealizedPnl') is not None and pos.get('notional') is not None:
                    try:
                        # Calculate percentage as (unrealizedPnl / notional) * 100
                        percentage = (float(pos['unrealizedPnl']) / float(pos['notional'])) * 100
                    except (ValueError, ZeroDivisionError):
                        percentage = None

                open_positions.append({
                    'symbol': pos['symbol'],
                    'side': pos['side'],
                    'size': pos['contracts'],
                    'notional': pos['notional'],
                    'entryPrice': pos['entryPrice'],
                    'markPrice': pos['markPrice'],
                    'unrealizedPnl': pos['unrealizedPnl'],
                    'percentage': percentage,
                    'liquidationPrice': pos.get('liquidationPrice'),
                    'leverage': pos.get('leverage'),
                    'marginMode': pos.get('marginMode'),
                    'marginType': pos.get('marginType'),
                    'maintenanceMargin': pos.get('maintenanceMargin'),
                    'initialMargin': pos.get('initialMargin'),
                    'marginRatio': pos.get('marginRatio'),
                })

        return open_positions

    except Exception as exc:
        print(f"Error: Failed to fetch Bybit positions: {exc}")
        return []


def fetch_bybit_account_balance(exchange: ccxt.Exchange) -> Dict[str, Any]:
    """Fetch account balance information from Bybit.

    Returns a dictionary with account balance details.
    """
    try:
        # Fetch account balance
        balance = exchange.fetch_balance()

        # Extract relevant balance information
        account_info = {
            'total_equity': balance.get('info', {}).get('totalEquity'),
            'total_wallet_balance': balance.get('info', {}).get('totalWalletBalance'),
            'total_unrealized_pnl': balance.get('info', {}).get('totalUnrealizedPnl'),
            'total_margin_balance': balance.get('info', {}).get('totalMarginBalance'),
            'total_initial_margin': balance.get('info', {}).get('totalInitialMargin'),
            'total_maintenance_margin': balance.get('info', {}).get('totalMaintenanceMargin'),
            'total_position_margin': balance.get('info', {}).get('totalPositionMargin'),
            'total_order_margin': balance.get('info', {}).get('totalOrderMargin'),
            'available_balance': balance.get('info', {}).get('availableBalance'),
            'used_margin': balance.get('info', {}).get('usedMargin'),
            'free_margin': balance.get('info', {}).get('freeMargin'),
        }

        return account_info

    except Exception as exc:
        print(f"Error: Failed to fetch Bybit account balance: {exc}")
        return {}
