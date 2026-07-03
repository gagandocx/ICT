"""
Premium/Discount Module - Zone Classification

Determines whether price is in a premium (above equilibrium) or discount
(below equilibrium) zone relative to the HTF swing range.

Rule: Only go long in discount zones, only go short in premium zones.
This ensures entries are taken at favorable prices within the market range.
"""


def calculate_equilibrium(swing_high, swing_low):
    """
    Calculate the equilibrium (50%) level of a swing range.

    Parameters
    ----------
    swing_high : float
        The swing high price level (top of range)
    swing_low : float
        The swing low price level (bottom of range)

    Returns
    -------
    float
        The equilibrium (midpoint) price level
    """
    return (swing_high + swing_low) / 2.0


def is_premium(price, equilibrium):
    """
    Check if price is in the premium zone (above equilibrium).

    Prices in premium are considered expensive. Only short entries
    should be taken in premium zones.

    Parameters
    ----------
    price : float
        Current price to check
    equilibrium : float
        The equilibrium level from calculate_equilibrium()

    Returns
    -------
    bool
        True if price is above the equilibrium (premium zone)
    """
    return price > equilibrium


def is_discount(price, equilibrium):
    """
    Check if price is in the discount zone (below equilibrium).

    Prices in discount are considered cheap. Only long entries
    should be taken in discount zones.

    Parameters
    ----------
    price : float
        Current price to check
    equilibrium : float
        The equilibrium level from calculate_equilibrium()

    Returns
    -------
    bool
        True if price is below the equilibrium (discount zone)
    """
    return price < equilibrium
