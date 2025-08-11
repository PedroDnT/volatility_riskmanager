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


def main() -> None:
    """Main routine for fetching Bybit positions."""
    # Load environment variables from .env file
    load_dotenv()

    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")

    if not api_key or not api_secret:
        print("Error: BYBIT_API_KEY or BYBIT_API_SECRET not found in .env file.")
        print("Please create a .env file with these variables:")
        print("BYBIT_API_KEY=your_api_key_here")
        print("BYBIT_API_SECRET=your_api_secret_here")
        return

    # For standalone execution, create an exchange instance
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'sandbox': False,  # Set to True for testnet
        'options': {
            'defaultType': 'linear',  # For USDT perpetual contracts
        }
    })

    print("Fetching open positions from Bybit...")
    
    # Fetch current Bybit positions
    positions = fetch_bybit_positions(exchange)
    
    # Fetch account balance information
    account_balance = fetch_bybit_account_balance(exchange)
    
    # Display account summary
    if account_balance:
        print("\n=== Account Summary ===")
        print("=" * 50)
        if account_balance.get('total_equity'):
            print(f"Total Equity: ${float(account_balance['total_equity']):.2f}")
        if account_balance.get('total_wallet_balance'):
            print(f"Wallet Balance: ${float(account_balance['total_wallet_balance']):.2f}")
        if account_balance.get('total_unrealized_pnl'):
            print(f"Total Unrealized PnL: ${float(account_balance['total_unrealized_pnl']):.2f}")
        if account_balance.get('available_balance'):
            print(f"Available Balance: ${float(account_balance['available_balance']):.2f}")
        if account_balance.get('used_margin'):
            print(f"Used Margin: ${float(account_balance['used_margin']):.2f}")
        if account_balance.get('free_margin'):
            print(f"Free Margin: ${float(account_balance['free_margin']):.2f}")
        print("-" * 50)
    
    if positions:
        print(f"\nFound {len(positions)} open position(s):")
        print("=" * 80)
        for i, pos in enumerate(positions, 1):
            # Debug: Print raw percentage value
            raw_percentage = pos.get('percentage')
            print(f"DEBUG: Raw percentage for {pos['symbol']}: {raw_percentage} (type: {type(raw_percentage)})")
            
            # Handle None values for PnL and percentage
            if pos['unrealizedPnl'] is not None and pos['percentage'] is not None:
                try:
                    percentage_val = float(pos['percentage'])
                    pnl_str = f"PnL: {pos['unrealizedPnl']:.2f} ({percentage_val:.2f}%)"
                except (ValueError, TypeError):
                    pnl_str = f"PnL: {pos['unrealizedPnl']:.2f} (percentage: {pos['percentage']})"
            elif pos['unrealizedPnl'] is not None:
                pnl_str = f"PnL: {pos['unrealizedPnl']:.2f} (percentage: N/A)"
            else:
                pnl_str = "PnL: N/A"
            
            print(f"Position {i}:")
            print(f"  Symbol: {pos['symbol']}")
            print(f"  Side: {pos['side'].upper()}")
            print(f"  Size: {pos['size']} contracts")
            print(f"  Notional: ${pos['notional']:.2f}")
            print(f"  Entry Price: {pos['entryPrice']}")
            print(f"  Mark Price: {pos['markPrice']}")
            print(f"  {pnl_str}")
            
            # Display liquidation and margin information
            if pos.get('liquidationPrice'):
                print(f"  Liquidation Price: {pos['liquidationPrice']}")
            if pos.get('leverage'):
                print(f"  Leverage: {pos['leverage']}x")
            if pos.get('marginMode'):
                print(f"  Margin Mode: {pos['marginMode']}")
            if pos.get('marginType'):
                print(f"  Margin Type: {pos['marginType']}")
            if pos.get('initialMargin'):
                print(f"  Initial Margin: ${pos['initialMargin']:.2f}")
            if pos.get('maintenanceMargin'):
                print(f"  Maintenance Margin: ${pos['maintenanceMargin']:.2f}")
            if pos.get('marginRatio'):
                print(f"  Margin Ratio: {pos['marginRatio']:.4f}")
            
            print("-" * 50)
        
        print("\nJSON format:")
        print(json.dumps(positions, indent=2))
        
        if account_balance:
            print("\nAccount Balance JSON:")
            print(json.dumps(account_balance, indent=2))
    else:
        print("No open positions found or unable to fetch positions.")


if __name__ == "__main__":
    main()
