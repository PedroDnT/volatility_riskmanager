def _hours_per_bar(timeframe: str) -> int:
    """
    Converts a timeframe string (e.g., '4h', '1d') to the number of hours.
    """
    try:
        if timeframe.endswith('h'):
            return int(timeframe[:-1])
        if timeframe.endswith('d'):
            return int(timeframe[:-1]) * 24
    except (ValueError, TypeError):
        pass
    # default to 4h if unknown
    return 4
