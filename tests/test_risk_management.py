"""
Tests for ict_bot/risk_management.py

Tests position sizing, daily loss limits, and SL/TP validation.
"""

import pytest

from ict_bot.risk_management import (
    calculate_position_size,
    check_daily_loss_limit,
    can_take_trade,
    validate_sl_tp,
)


class TestCalculatePositionSize:
    """Tests for calculate_position_size()."""

    def test_basic_position_size_calculation(self):
        """Position size with known inputs should produce expected volume."""
        # $10,000 balance, 1% risk = $100 risk amount
        # Entry 15000, SL 14990 => sl_distance = 10
        # Volume = 100 / (10 * 1.0) = 10.0
        result = calculate_position_size(10000.0, 0.01, 15000.0, 14990.0)
        assert result["valid"] is True
        assert result["risk_amount"] == 100.0
        assert result["sl_distance"] == 10.0
        assert result["volume"] == 10.0

    def test_position_size_respects_volume_step(self):
        """Volume should be rounded to the nearest volume_step."""
        # $10,000 balance, 1% risk = $100
        # Entry 15000, SL 14993 => sl_distance = 7
        # Volume = 100 / (7 * 1.0) = 14.2857... -> rounded to 14.29 (step=0.01)
        result = calculate_position_size(10000.0, 0.01, 15000.0, 14993.0)
        assert result["valid"] is True
        assert result["volume"] == 14.29

    def test_zero_balance_returns_invalid(self):
        """Zero balance should return invalid result."""
        result = calculate_position_size(0.0, 0.01, 15000.0, 14990.0)
        assert result["valid"] is False
        assert result["volume"] == 0.0

    def test_sl_at_entry_returns_invalid(self):
        """Stop loss at entry price (zero distance) should return invalid."""
        result = calculate_position_size(10000.0, 0.01, 15000.0, 15000.0)
        assert result["valid"] is False

    def test_negative_balance_returns_invalid(self):
        """Negative balance should return invalid result."""
        result = calculate_position_size(-1000.0, 0.01, 15000.0, 14990.0)
        assert result["valid"] is False

    def test_volume_below_minimum_returns_invalid(self):
        """If calculated volume is below volume_min, result is invalid."""
        # $100 balance, 0.1% risk = $0.10
        # SL distance = 100 points
        # Volume = 0.10 / (100 * 1.0) = 0.001 < 0.01 min
        result = calculate_position_size(100.0, 0.001, 15000.0, 14900.0)
        assert result["valid"] is False

    def test_custom_symbol_info(self):
        """Custom symbol info should override defaults."""
        symbol_info = {
            "contract_size": 10.0,
            "volume_min": 0.1,
            "volume_max": 50.0,
            "volume_step": 0.1,
        }
        # $10,000 balance, 1% risk = $100
        # SL distance = 10
        # Volume = 100 / (10 * 10.0) = 1.0
        result = calculate_position_size(10000.0, 0.01, 15000.0, 14990.0,
                                         symbol_info=symbol_info)
        assert result["valid"] is True
        assert result["volume"] == 1.0


class TestCheckDailyLossLimit:
    """Tests for check_daily_loss_limit()."""

    def test_limit_not_reached_with_small_loss(self):
        """Daily loss below 3% should not trigger limit."""
        result = check_daily_loss_limit(-100.0, 10000.0, max_loss_percent=0.03)
        assert result["limit_reached"] is False
        assert result["remaining"] > 0

    def test_limit_reached_at_3_percent(self):
        """Daily loss of exactly 3% should trigger limit."""
        result = check_daily_loss_limit(-300.0, 10000.0, max_loss_percent=0.03)
        assert result["limit_reached"] is True
        assert result["remaining"] == 0.0

    def test_limit_reached_above_3_percent(self):
        """Daily loss above 3% should definitely trigger limit."""
        result = check_daily_loss_limit(-500.0, 10000.0, max_loss_percent=0.03)
        assert result["limit_reached"] is True

    def test_positive_pnl_does_not_trigger_limit(self):
        """Positive daily PnL should never trigger loss limit."""
        result = check_daily_loss_limit(200.0, 10000.0, max_loss_percent=0.03)
        assert result["limit_reached"] is False
        assert result["current_loss_percent"] == 0.0

    def test_max_loss_amount_calculation(self):
        """max_loss_amount should be balance * max_loss_percent."""
        result = check_daily_loss_limit(-50.0, 10000.0, max_loss_percent=0.03)
        assert result["max_loss_amount"] == 300.0


class TestCanTakeTrade:
    """Tests for can_take_trade()."""

    def test_can_trade_with_no_daily_loss(self):
        """Should allow trading with zero daily loss."""
        assert can_take_trade(0.0, 10000.0) is True

    def test_cannot_trade_when_limit_reached(self):
        """Should block trading when daily loss >= 3%."""
        assert can_take_trade(-300.0, 10000.0) is False

    def test_cannot_trade_with_zero_balance(self):
        """Should block trading with zero balance."""
        assert can_take_trade(0.0, 0.0) is False


class TestValidateSlTp:
    """Tests for validate_sl_tp()."""

    def test_valid_long_trade(self):
        """Long trade: SL below entry, TP above entry is valid."""
        result = validate_sl_tp(15000.0, 14990.0, 15030.0, "long")
        assert result["valid"] is True
        assert result["risk_reward"] == 3.0  # 30/10

    def test_valid_short_trade(self):
        """Short trade: SL above entry, TP below entry is valid."""
        result = validate_sl_tp(15000.0, 15010.0, 14970.0, "short")
        assert result["valid"] is True
        assert result["risk_reward"] == 3.0  # 30/10

    def test_invalid_long_sl_above_entry(self):
        """Long trade with SL above entry should be invalid."""
        result = validate_sl_tp(15000.0, 15010.0, 15030.0, "long")
        assert result["valid"] is False

    def test_invalid_short_sl_below_entry(self):
        """Short trade with SL below entry should be invalid."""
        result = validate_sl_tp(15000.0, 14990.0, 14970.0, "short")
        assert result["valid"] is False

    def test_invalid_direction(self):
        """Invalid direction string should return invalid."""
        result = validate_sl_tp(15000.0, 14990.0, 15030.0, "sideways")
        assert result["valid"] is False
