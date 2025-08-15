from .position_risk_manager import PositionRiskManager


def main():
    """Main execution function."""
    # Initialize risk manager
    manager = PositionRiskManager(sandbox=False)

    # Fetch and analyze positions
    positions = manager.fetch_positions()

    if not positions:
        print("No positions to analyze. Exiting.")
        return

    # Analyze all positions
    manager.analyze_all_positions()

    # Generate and print report
    report = manager.generate_report()
    print("\n" + report)

    # Export to JSON
    manager.export_to_json()

    # Print summary table
    print("\n" + "=" * 80)
    print("QUICK REFERENCE TABLE")
    print("=" * 80)
    print(f"{'Symbol':<15} {'Side':<5} {'Entry':<10} {'SL':<10} {'TP':<10} {'R:R':<6} {'Risk%':<7} {'k/m':<9}")
    print("-" * 80)

    for position in positions:
        symbol = position['symbol']
        analysis = manager.risk_analysis.get(symbol, {})

        if analysis and 'stop_loss' in analysis:
            print(f"{symbol:<15} {analysis['side'].upper():<5} "
                  f"${analysis['entry_price']:<9.4f} "
                  f"${analysis['stop_loss']:<9.4f} "
                  f"${analysis['take_profit']:<9.4f} "
                  f"{analysis['risk_reward_ratio']:<5.1f}:1 "
                  f"{analysis['risk_target_pct']*100:<6.2f}% "
                  f"{analysis['k_multiplier']:.1f}/{analysis['m_multiplier']:.1f}")


if __name__ == "__main__":
    main()
