"""
Tests for ict_bot/entry_model.py

Tests the sequential state machine entry model:
WAITING_FOR_SWEEP -> WAITING_FOR_MSS -> WAITING_FOR_FVG -> READY_TO_ENTER
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from ict_bot.entry_model import EntryModel, EntryState


class TestEntryModelStates:
    """Tests for the state machine behavior."""

    def test_initial_state_is_waiting_for_sweep(self):
        """Entry model should start in WAITING_FOR_SWEEP state."""
        model = EntryModel()
        assert model.current_state == "waiting_for_sweep"

    def test_reset_returns_to_initial_state(self):
        """reset() should return the model to WAITING_FOR_SWEEP."""
        model = EntryModel()
        # Manually advance state
        model.state = EntryState.WAITING_FOR_MSS
        model.sweep_info = {"type": "sweep_high"}
        model.reset()
        assert model.current_state == "waiting_for_sweep"
        assert model.sweep_info is None
        assert model.mss_info is None
        assert model.fvg_info is None

    def test_cannot_advance_to_mss_without_sweep(self):
        """
        Feeding candles that create an MSS pattern but no sweep should
        NOT advance past WAITING_FOR_SWEEP.
        """
        model = EntryModel(lookback=3)
        # Feed candles with structure but no equal levels/sweeps
        for i in range(20):
            candle = {
                "time": datetime(2024, 1, 1, 10, i),
                "open": 100 + i * 0.5,
                "high": 101 + i * 0.5,
                "low": 99 + i * 0.5,
                "close": 100.5 + i * 0.5,
            }
            model.update(candle)
        # Should still be waiting for sweep since no equal levels exist
        assert model.current_state == "waiting_for_sweep"

    def test_needs_minimum_candles_for_sweep(self):
        """check_liquidity_sweep requires at least 10 candles."""
        model = EntryModel()
        for i in range(9):
            candle = {
                "time": datetime(2024, 1, 1, 10, i),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            }
            result = model.update(candle)
            assert result is None
        assert model.current_state == "waiting_for_sweep"


class TestEntryModelSequentialFlow:
    """Tests for the full sequential confirmation flow."""

    def _build_sweep_candles(self):
        """
        Build a candle sequence that creates equal highs and then sweeps them.

        Uses tolerance_pips=2 and min_sweep_pips=2 to ensure proper detection.
        Creates two highs at 150/151 (within tolerance 2). All lows are spaced
        more than 2 apart so no equal lows form. Highs after idx 1 are all
        below 148 so they don't group with the 150/151 pair.
        """
        candles = []
        base_time = datetime(2024, 1, 1, 10, 0)

        # Candle 0: high=150, low=144
        candles.append({"time": base_time, "open": 147, "high": 150, "low": 144, "close": 148})
        # Candle 1: high=151 (equal with 150, tolerance=2), low=147
        candles.append({"time": base_time + timedelta(minutes=1), "open": 148, "high": 151, "low": 147, "close": 149})
        # Candles 2-9: descend with lows each >2 apart, highs all < 148
        # Lows: 130, 125, 120, 115, 110, 105, 100, 95 (all 5 apart)
        # Highs: 135, 130, 125, 120, 115, 110, 105, 100 (all < 148)
        candles.append({"time": base_time + timedelta(minutes=2), "open": 140, "high": 142, "low": 130, "close": 135})
        candles.append({"time": base_time + timedelta(minutes=3), "open": 135, "high": 137, "low": 125, "close": 130})
        candles.append({"time": base_time + timedelta(minutes=4), "open": 130, "high": 132, "low": 120, "close": 125})
        candles.append({"time": base_time + timedelta(minutes=5), "open": 125, "high": 127, "low": 115, "close": 120})
        candles.append({"time": base_time + timedelta(minutes=6), "open": 120, "high": 122, "low": 110, "close": 115})
        candles.append({"time": base_time + timedelta(minutes=7), "open": 115, "high": 117, "low": 105, "close": 110})
        candles.append({"time": base_time + timedelta(minutes=8), "open": 110, "high": 112, "low": 100, "close": 105})
        candles.append({"time": base_time + timedelta(minutes=9), "open": 105, "high": 107, "low": 95, "close": 100})
        # Candle 10: SWEEP - high=154 > 150.5+2=152.5, close=145 < 150.5
        candles.append({"time": base_time + timedelta(minutes=10), "open": 100, "high": 154, "low": 98, "close": 145})

        return candles

    def test_sweep_advances_state_to_waiting_for_mss(self):
        """After detecting a liquidity sweep, state advances to WAITING_FOR_MSS."""
        model = EntryModel(lookback=3, tolerance_pips=2, min_sweep_pips=2)
        candles = self._build_sweep_candles()

        for candle in candles:
            model.update(candle)

        assert model.current_state == "waiting_for_mss"
        assert model.sweep_info is not None
        assert model.sweep_info["type"] == "sweep_high"

    def test_update_returns_none_without_full_sequence(self):
        """update() should return None until the full sequence completes."""
        model = EntryModel(lookback=3, tolerance_pips=2, min_sweep_pips=2)
        candles = self._build_sweep_candles()

        for candle in candles:
            result = model.update(candle)
            # Should not generate a signal from sweep alone
            assert result is None

    def test_mss_direction_must_align_with_sweep(self):
        """
        After sweep_high, only bearish_mss should advance state.
        After sweep_low, only bullish_mss should advance state.
        """
        model = EntryModel(lookback=3, tolerance_pips=2, min_sweep_pips=2)
        candles = self._build_sweep_candles()

        for candle in candles:
            model.update(candle)

        # Verify sweep was detected as sweep_high
        assert model.current_state == "waiting_for_mss"
        assert model.sweep_info["type"] == "sweep_high"
        # The model now needs a bearish_mss to advance
        # Feed candles that only go up (no bearish MSS possible)
        for i in range(15):
            candle = {
                "time": datetime(2024, 1, 1, 10, 20 + i),
                "open": 160 + i,
                "high": 162 + i,
                "low": 159 + i,
                "close": 161 + i,
            }
            model.update(candle)

        # Should still be waiting for MSS since only uptrend was fed
        assert model.current_state == "waiting_for_mss"


class TestEntryModelSignalGeneration:
    """Tests for entry signal generation."""

    def test_entry_signal_has_required_keys(self):
        """When a signal is generated, it should have all required keys."""
        model = EntryModel(lookback=3, tolerance_pips=5, min_sweep_pips=2)

        # Manually set up the model to be in READY_TO_ENTER state
        model.state = EntryState.READY_TO_ENTER
        model.sweep_info = {
            "type": "sweep_high",
            "level": 110.0,
            "sweep_index": 10,
            "sweep_price": 113.0,
            "close_price": 108.0,
            "time": datetime(2024, 1, 1, 10, 10),
        }
        model.mss_info = {
            "type": "bearish_mss",
            "break_index": 15,
            "broken_level": 105.0,
            "swing_index": 12,
            "time": datetime(2024, 1, 1, 10, 15),
        }
        model.fvg_info = {
            "type": "bearish_fvg",
            "high": 107.0,
            "low": 103.0,
            "midpoint": 105.0,
            "index": 16,
            "time": datetime(2024, 1, 1, 10, 16),
            "filled": False,
        }

        # Add candle buffer for opposing liquidity search
        for i in range(20):
            model.candle_buffer.append({
                "time": datetime(2024, 1, 1, 10, i),
                "open": 108 - i * 0.2,
                "high": 110 - i * 0.2,
                "low": 106 - i * 0.2,
                "close": 107 - i * 0.2,
            })

        signal = model.generate_entry_signal()
        assert signal is not None
        assert "direction" in signal
        assert "entry_price" in signal
        assert "stop_loss" in signal
        assert "take_profit" in signal
        assert "risk_reward" in signal
        assert signal["direction"] == "short"

    def test_entry_price_is_fvg_midpoint(self):
        """Entry price should be the FVG 50% midpoint."""
        model = EntryModel(lookback=3)
        model.state = EntryState.READY_TO_ENTER
        model.sweep_info = {
            "type": "sweep_high",
            "level": 110.0,
            "sweep_index": 10,
            "sweep_price": 113.0,
            "close_price": 108.0,
            "time": datetime(2024, 1, 1, 10, 10),
        }
        model.mss_info = {
            "type": "bearish_mss",
            "break_index": 15,
            "broken_level": 105.0,
            "swing_index": 12,
            "time": datetime(2024, 1, 1, 10, 15),
        }
        model.fvg_info = {
            "type": "bearish_fvg",
            "high": 108.0,
            "low": 104.0,
            "midpoint": 106.0,
            "index": 16,
            "time": datetime(2024, 1, 1, 10, 16),
            "filled": False,
        }

        for i in range(20):
            model.candle_buffer.append({
                "time": datetime(2024, 1, 1, 10, i),
                "open": 108 - i * 0.2,
                "high": 110 - i * 0.2,
                "low": 106 - i * 0.2,
                "close": 107 - i * 0.2,
            })

        signal = model.generate_entry_signal()
        assert signal is not None
        # entry_price = (108 + 104) / 2 = 106
        assert signal["entry_price"] == 106.0
