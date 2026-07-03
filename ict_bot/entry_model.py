"""
Entry Model Module - Sequential Confirmation Entry Model

Implements the ICT sequential entry model as a state machine that enforces
strict ordering during Kill Zones:

1. WAITING_FOR_SWEEP - Monitor for liquidity sweep
2. WAITING_FOR_MSS - After sweep, wait for Market Structure Shift
3. WAITING_FOR_FVG - After MSS, wait for Fair Value Gap in the MSS leg
4. READY_TO_ENTER - FVG found, generate entry signal

No step can be skipped. Each confirmation must happen in sequence.
"""

import pandas as pd
import numpy as np
from enum import Enum

from ict_bot.liquidity import detect_equal_levels, detect_liquidity_sweep
from ict_bot.market_structure import detect_swing_points, detect_mss
from ict_bot.fvg import detect_fvg, get_fvg_midpoint


class EntryState(Enum):
    """States of the sequential entry model."""
    WAITING_FOR_SWEEP = "waiting_for_sweep"
    WAITING_FOR_MSS = "waiting_for_mss"
    WAITING_FOR_FVG = "waiting_for_fvg"
    READY_TO_ENTER = "ready_to_enter"


class EntryModel:
    """
    Sequential confirmation entry model implementing ICT concepts.

    The model enforces strict sequential ordering:
    Liquidity Sweep -> MSS -> FVG -> Entry Signal

    Parameters
    ----------
    lookback : int
        Number of candles to look back for swing detection. Default 5.
    tolerance_pips : float
        Tolerance for equal level detection. Default 5.
    min_sweep_pips : float
        Minimum sweep distance. Default 2.
    """

    def __init__(self, lookback=5, tolerance_pips=5, min_sweep_pips=2):
        self.lookback = lookback
        self.tolerance_pips = tolerance_pips
        self.min_sweep_pips = min_sweep_pips

        self.state = EntryState.WAITING_FOR_SWEEP
        self.candle_buffer = []
        self.sweep_info = None
        self.mss_info = None
        self.fvg_info = None
        self.entry_signal = None

    def reset(self):
        """
        Reset the entry model state.

        Called after an entry is taken or when the kill zone ends.
        Clears all detected confirmations and returns to initial state.
        """
        self.state = EntryState.WAITING_FOR_SWEEP
        self.candle_buffer = []
        self.sweep_info = None
        self.mss_info = None
        self.fvg_info = None
        self.entry_signal = None

    def update(self, candle_data):
        """
        Process a new 1m candle and advance the state machine.

        Parameters
        ----------
        candle_data : dict
            Candle data with keys: open, high, low, close, time

        Returns
        -------
        dict or None
            Entry signal if READY_TO_ENTER state is reached, else None.
        """
        self.candle_buffer.append(candle_data)

        if self.state == EntryState.WAITING_FOR_SWEEP:
            self.check_liquidity_sweep()
        elif self.state == EntryState.WAITING_FOR_MSS:
            self.check_mss()
        elif self.state == EntryState.WAITING_FOR_FVG:
            self.check_fvg()

        if self.state == EntryState.READY_TO_ENTER:
            return self.generate_entry_signal()

        return None

    def check_liquidity_sweep(self):
        """
        Check for a liquidity sweep in the current candle buffer.

        Uses the liquidity module to detect equal levels and sweeps.
        Only transitions to WAITING_FOR_MSS if a sweep is detected.
        """
        if len(self.candle_buffer) < 10:
            return

        df = pd.DataFrame(self.candle_buffer)

        levels = detect_equal_levels(df, tolerance_pips=self.tolerance_pips)
        if not levels:
            return

        sweeps = detect_liquidity_sweep(df, levels, min_sweep_pips=self.min_sweep_pips)
        if sweeps:
            # Take the most recent sweep
            self.sweep_info = sweeps[-1]
            self.state = EntryState.WAITING_FOR_MSS

    def check_mss(self):
        """
        Check for a Market Structure Shift after a liquidity sweep.

        Only called when state is WAITING_FOR_MSS (after sweep detected).
        Uses the market_structure module to detect MSS events that occur
        after the sweep candle.
        """
        if len(self.candle_buffer) < self.lookback * 2 + 1:
            return

        df = pd.DataFrame(self.candle_buffer)
        swings = detect_swing_points(df, lookback=self.lookback)

        if not swings:
            return

        mss_events = detect_mss(df, swings)
        if not mss_events:
            return

        # Find MSS that occurs after the sweep
        sweep_idx = self.sweep_info["sweep_index"]
        for mss_event in mss_events:
            if mss_event["break_index"] > sweep_idx:
                # Validate MSS direction aligns with sweep direction
                if (self.sweep_info["type"] == "sweep_high"
                        and mss_event["type"] == "bearish_mss"):
                    self.mss_info = mss_event
                    self.state = EntryState.WAITING_FOR_FVG
                    break
                elif (self.sweep_info["type"] == "sweep_low"
                      and mss_event["type"] == "bullish_mss"):
                    self.mss_info = mss_event
                    self.state = EntryState.WAITING_FOR_FVG
                    break

    def check_fvg(self):
        """
        Check for a Fair Value Gap within the MSS leg.

        Only called when state is WAITING_FOR_FVG (after MSS detected).
        Looks for FVGs that form after the MSS break candle and align
        with the expected direction.
        """
        if len(self.candle_buffer) < 3:
            return

        df = pd.DataFrame(self.candle_buffer)
        fvgs = detect_fvg(df)

        if not fvgs:
            return

        # Find FVG that forms after the MSS break
        mss_break_idx = self.mss_info["break_index"]
        expected_type = ("bearish_fvg" if self.mss_info["type"] == "bearish_mss"
                         else "bullish_fvg")

        valid_fvgs = []
        for fvg_item in fvgs:
            if (fvg_item["index"] >= mss_break_idx
                    and fvg_item["type"] == expected_type):
                valid_fvgs.append(fvg_item)

        if valid_fvgs:
            # Select the highest FVG in the MSS leg for stop loss placement
            if expected_type == "bearish_fvg":
                # For bearish, "highest" means the one with the highest price
                self.fvg_info = max(valid_fvgs, key=lambda f: f["high"])
            else:
                # For bullish, "highest" means the one with the lowest price
                # (deepest into discount)
                self.fvg_info = min(valid_fvgs, key=lambda f: f["low"])

            self.state = EntryState.READY_TO_ENTER

    def generate_entry_signal(self):
        """
        Generate entry parameters when all confirmations are met.

        Returns
        -------
        dict or None
            Entry signal with:
            - direction: 'long' or 'short'
            - entry_price: FVG 50% midpoint (limit order level)
            - stop_loss: above/below the candle that created the highest FVG
            - take_profit: opposing liquidity level
            - risk_reward: estimated R:R ratio
            - sweep_info: the liquidity sweep details
            - mss_info: the MSS details
            - fvg_info: the FVG details
        """
        if not all([self.sweep_info, self.mss_info, self.fvg_info]):
            return None

        df = pd.DataFrame(self.candle_buffer)
        entry_price = get_fvg_midpoint(self.fvg_info)

        # Determine direction based on MSS type
        if self.mss_info["type"] == "bearish_mss":
            direction = "short"
            # Stop loss above the candle that created the highest FVG
            fvg_candle_idx = self.fvg_info["index"]
            if fvg_candle_idx < len(df):
                stop_loss = df["high"].iloc[fvg_candle_idx] + 1.0
            else:
                stop_loss = self.fvg_info["high"] + 1.0

            # Take profit at opposing liquidity (swing low / sweep low)
            take_profit = self._find_opposing_liquidity(df, direction)

        else:  # bullish_mss
            direction = "long"
            # Stop loss below the candle that created the highest FVG
            fvg_candle_idx = self.fvg_info["index"]
            if fvg_candle_idx < len(df):
                stop_loss = df["low"].iloc[fvg_candle_idx] - 1.0
            else:
                stop_loss = self.fvg_info["low"] - 1.0

            # Take profit at opposing liquidity (swing high / sweep high)
            take_profit = self._find_opposing_liquidity(df, direction)

        # Calculate risk/reward
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        risk_reward = reward / risk if risk > 0 else 0.0

        self.entry_signal = {
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": risk_reward,
            "sweep_info": self.sweep_info,
            "mss_info": self.mss_info,
            "fvg_info": self.fvg_info,
        }

        return self.entry_signal

    def _find_opposing_liquidity(self, df, direction):
        """
        Find opposing liquidity for take profit placement.

        For short entries, look for swing lows or previous liquidity below.
        For long entries, look for swing highs or previous liquidity above.

        Parameters
        ----------
        df : pd.DataFrame
            OHLC DataFrame
        direction : str
            'long' or 'short'

        Returns
        -------
        float
            Take profit price level
        """
        swings = detect_swing_points(df, lookback=self.lookback)

        if direction == "short":
            # Look for swing lows below current price
            swing_lows = [s for s in swings if s["type"] == "swing_low"]
            if swing_lows:
                # Take the most recent swing low
                return swing_lows[-1]["price"]
            # Fallback: use the lowest low in the buffer
            return df["low"].min()
        else:
            # Look for swing highs above current price
            swing_highs = [s for s in swings if s["type"] == "swing_high"]
            if swing_highs:
                # Take the most recent swing high
                return swing_highs[-1]["price"]
            # Fallback: use the highest high in the buffer
            return df["high"].max()

    @property
    def current_state(self):
        """Return the current state name as a string."""
        return self.state.value
