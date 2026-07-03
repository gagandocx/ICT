"""
Optimal Trade Entry (OTE) Module - Fibonacci Retracement Zones

The OTE zone is the 62-79% Fibonacci retracement level of a swing move.
After a Market Structure Shift (MSS), price often retraces into this zone
before continuing in the new direction. This is the ideal entry area.
"""


def calculate_ote_zone(swing_high, swing_low, direction):
    """
    Calculate the OTE zone (62-79% Fibonacci retracement).

    For a bullish setup (long entry):
        Price moved down from swing_high to swing_low, then reversed.
        OTE zone is 62-79% retracement from swing_low back toward swing_high.

    For a bearish setup (short entry):
        Price moved up from swing_low to swing_high, then reversed.
        OTE zone is 62-79% retracement from swing_high back toward swing_low.

    Parameters
    ----------
    swing_high : float
        The swing high price level
    swing_low : float
        The swing low price level
    direction : str
        'bullish' for long entries (retracement from low toward high)
        'bearish' for short entries (retracement from high toward low)

    Returns
    -------
    tuple of (float, float)
        (ote_low, ote_high) representing the OTE zone boundaries.
        ote_low is the lower price, ote_high is the upper price.
    """
    price_range = swing_high - swing_low

    if direction == "bullish":
        # After a bearish move (high to low), price reverses up.
        # Retracement is measured from the low back up.
        # 62% retracement from low = low + 0.62 * range
        # 79% retracement from low = low + 0.79 * range
        # But in Fibonacci: OTE is between 0.618 and 0.786 of the impulse move
        # For bullish entry: we want price to pull back DOWN into OTE
        # OTE zone is between 62% and 79% retracement of the new impulse
        ote_low = swing_low + (1 - 0.79) * price_range  # 79% retrace = deeper
        ote_high = swing_low + (1 - 0.62) * price_range  # 62% retrace = shallower

    elif direction == "bearish":
        # After a bullish move (low to high), price reverses down.
        # For bearish entry: we want price to pull back UP into OTE
        ote_low = swing_low + 0.62 * price_range  # 62% retrace from top
        ote_high = swing_low + 0.79 * price_range  # 79% retrace from top

    else:
        raise ValueError(f"direction must be 'bullish' or 'bearish', got '{direction}'")

    return (ote_low, ote_high)


def is_price_in_ote(price, ote_zone):
    """
    Check if a price is within the OTE zone.

    Parameters
    ----------
    price : float
        The price to check
    ote_zone : tuple of (float, float)
        (ote_low, ote_high) from calculate_ote_zone()

    Returns
    -------
    bool
        True if the price is within the OTE zone (inclusive)
    """
    ote_low, ote_high = ote_zone
    return ote_low <= price <= ote_high
