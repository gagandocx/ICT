"""
Risk Management Module - Position Sizing and Daily Loss Limits

Implements risk management rules for the ICT trading bot:
- 1% risk per trade based on stop loss distance
- 3% maximum daily loss limit
- Position size calculation based on account balance and symbol info
"""


def calculate_position_size(account_balance, risk_percent, entry_price,
                            stop_loss_price, symbol_info=None):
    """
    Calculate position size based on risk percentage and stop loss distance.

    Uses fixed fractional position sizing: risk a fixed percentage of account
    equity on each trade, with position size determined by the distance
    between entry and stop loss.

    Parameters
    ----------
    account_balance : float
        Current account balance/equity.
    risk_percent : float
        Percentage of account to risk per trade (e.g., 0.01 for 1%).
    entry_price : float
        Planned entry price.
    stop_loss_price : float
        Stop loss price level.
    symbol_info : dict or None
        Symbol information containing:
        - 'contract_size': contract size (e.g., 1 for NAS100 CFD)
        - 'volume_min': minimum lot size
        - 'volume_max': maximum lot size
        - 'volume_step': lot size increment
        - 'point': smallest price movement
        If None, defaults for NAS100 CFD are used.

    Returns
    -------
    dict
        Position sizing result with:
        - 'volume': calculated lot size
        - 'risk_amount': dollar amount at risk
        - 'sl_distance': distance in price from entry to SL
        - 'valid': bool indicating if the position size is valid
        - 'message': informational message
    """
    if account_balance <= 0:
        return {
            "volume": 0.0,
            "risk_amount": 0.0,
            "sl_distance": 0.0,
            "valid": False,
            "message": "Account balance must be positive",
        }

    if risk_percent <= 0 or risk_percent > 1.0:
        return {
            "volume": 0.0,
            "risk_amount": 0.0,
            "sl_distance": 0.0,
            "valid": False,
            "message": "Risk percent must be between 0 and 1.0",
        }

    sl_distance = abs(entry_price - stop_loss_price)
    if sl_distance == 0:
        return {
            "volume": 0.0,
            "risk_amount": 0.0,
            "sl_distance": 0.0,
            "valid": False,
            "message": "Stop loss cannot be at entry price",
        }

    # Default symbol info for NAS100 CFD
    if symbol_info is None:
        symbol_info = {
            "contract_size": 1.0,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "point": 0.01,
        }

    contract_size = symbol_info.get("contract_size", 1.0)
    volume_min = symbol_info.get("volume_min", 0.01)
    volume_max = symbol_info.get("volume_max", 100.0)
    volume_step = symbol_info.get("volume_step", 0.01)

    risk_amount = account_balance * risk_percent
    # Volume = risk_amount / (sl_distance * contract_size)
    volume = risk_amount / (sl_distance * contract_size)

    # Round to volume step
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step
        # Ensure precision
        decimals = len(str(volume_step).rstrip("0").split(".")[-1])
        volume = round(volume, decimals)

    # Clamp to min/max
    if volume < volume_min:
        return {
            "volume": 0.0,
            "risk_amount": risk_amount,
            "sl_distance": sl_distance,
            "valid": False,
            "message": (f"Calculated volume {volume:.4f} is below minimum "
                        f"{volume_min}"),
        }

    if volume > volume_max:
        volume = volume_max

    return {
        "volume": volume,
        "risk_amount": risk_amount,
        "sl_distance": sl_distance,
        "valid": True,
        "message": "Position size calculated successfully",
    }


def check_daily_loss_limit(daily_pnl, account_balance, max_loss_percent=0.03):
    """
    Check if the daily loss limit has been reached.

    Parameters
    ----------
    daily_pnl : float
        Current day's profit/loss (negative means loss).
    account_balance : float
        Account balance at the start of the day.
    max_loss_percent : float
        Maximum allowed daily loss as a fraction (e.g., 0.03 for 3%).

    Returns
    -------
    dict
        Result with:
        - 'limit_reached': bool, True if daily loss exceeds limit
        - 'current_loss_percent': current loss as fraction of balance
        - 'max_loss_amount': maximum allowed loss in currency
        - 'remaining': how much more can be lost before limit
    """
    if account_balance <= 0:
        return {
            "limit_reached": True,
            "current_loss_percent": 0.0,
            "max_loss_amount": 0.0,
            "remaining": 0.0,
        }

    max_loss_amount = account_balance * max_loss_percent
    current_loss = abs(min(daily_pnl, 0.0))
    current_loss_percent = current_loss / account_balance
    remaining = max(max_loss_amount - current_loss, 0.0)
    limit_reached = current_loss >= max_loss_amount

    return {
        "limit_reached": limit_reached,
        "current_loss_percent": current_loss_percent,
        "max_loss_amount": max_loss_amount,
        "remaining": remaining,
    }


def can_take_trade(daily_pnl, account_balance, max_loss_percent=0.03):
    """
    Determine if a new trade can be taken based on all risk rules.

    Combines daily loss limit check with other risk validations to
    provide a simple boolean answer.

    Parameters
    ----------
    daily_pnl : float
        Current day's profit/loss (negative means loss).
    account_balance : float
        Account balance at the start of the day.
    max_loss_percent : float
        Maximum allowed daily loss as a fraction (default 0.03 for 3%).

    Returns
    -------
    bool
        True if a new trade can be taken, False otherwise.
    """
    if account_balance <= 0:
        return False

    loss_check = check_daily_loss_limit(daily_pnl, account_balance, max_loss_percent)
    if loss_check["limit_reached"]:
        return False

    return True


def validate_sl_tp(entry_price, stop_loss, take_profit, direction):
    """
    Validate that stop loss and take profit levels are logically correct.

    Parameters
    ----------
    entry_price : float
        The planned entry price.
    stop_loss : float
        The stop loss price.
    take_profit : float
        The take profit price.
    direction : str
        Trade direction: 'long' or 'short'.

    Returns
    -------
    dict
        Validation result with:
        - 'valid': bool
        - 'message': str describing any issue
        - 'risk_reward': float R:R ratio if valid
    """
    if direction == "long":
        if stop_loss >= entry_price:
            return {
                "valid": False,
                "message": "Stop loss must be below entry for long trades",
                "risk_reward": 0.0,
            }
        if take_profit <= entry_price:
            return {
                "valid": False,
                "message": "Take profit must be above entry for long trades",
                "risk_reward": 0.0,
            }
    elif direction == "short":
        if stop_loss <= entry_price:
            return {
                "valid": False,
                "message": "Stop loss must be above entry for short trades",
                "risk_reward": 0.0,
            }
        if take_profit >= entry_price:
            return {
                "valid": False,
                "message": "Take profit must be below entry for short trades",
                "risk_reward": 0.0,
            }
    else:
        return {
            "valid": False,
            "message": f"Invalid direction: {direction}. Must be 'long' or 'short'",
            "risk_reward": 0.0,
        }

    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)
    risk_reward = reward / risk if risk > 0 else 0.0

    return {
        "valid": True,
        "message": "SL/TP levels are valid",
        "risk_reward": risk_reward,
    }
