"""Tests for the guardrails module."""

from __future__ import annotations

import pytest

from app.guardrails import GuardrailError, validate_directives
from app.models import (
    DirectiveInterpretation,
    DirectiveType,
    HourEntry,
    StructuredAdjustment,
)


def _make_hours() -> list[HourEntry]:
    """Create a standard 24-hour demand/solar/tariff array."""
    base_demand = [
        90, 85, 80, 80, 85, 95, 110, 130, 150, 165,
        175, 180, 185, 180, 170, 165, 170, 185, 205, 215,
        205, 175, 135, 105,
    ]
    base_solar = [
        0, 0, 0, 0, 0, 0, 5, 20, 50, 90,
        130, 160, 180, 170, 140, 90, 45, 10, 0, 0,
        0, 0, 0, 0,
    ]
    tariff = [
        6, 6, 5, 5, 5, 6, 8, 10, 12, 14,
        16, 16, 15, 14, 13, 14, 18, 22, 28, 30,
        26, 18, 10, 7,
    ]
    return [
        HourEntry(hour=h, demand_kwh=base_demand[h], solar_kwh=base_solar[h], tariff_bdt_per_kwh=tariff[h])
        for h in range(24)
    ]


class TestValidateDirectives:
    """validate_directives should normalise and reject bad input."""

    def test_no_op_directive(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=False,
                directive_type=DirectiveType.NO_OP,
                structured_adjustment=None,
                explanation="distractor",
            )
        ]
        result = validate_directives(directives, hours, note_count=1)
        assert len(result) == 1
        assert result[0].directive_type == DirectiveType.NO_OP
        assert result[0].applies is False

    def test_solar_reduction_valid(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.SOLAR_REDUCTION,
                structured_adjustment=StructuredAdjustment(
                    hours=[12, 13], factor=0.25
                ),
                explanation="panel cleaning",
            )
        ]
        result = validate_directives(directives, hours, note_count=1)
        assert result[0].directive_type == DirectiveType.SOLAR_REDUCTION
        assert result[0].applies is True

    def test_rejects_bad_factor(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.SOLAR_REDUCTION,
                structured_adjustment=StructuredAdjustment(
                    hours=[12], factor=1.5
                ),
                explanation="bad",
            )
        ]
        with pytest.raises(GuardrailError, match="factor must be in"):
            validate_directives(directives, hours, note_count=1)

    def test_rejects_non_ascending_hours(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.NO_CHARGE_WINDOW,
                structured_adjustment=StructuredAdjustment(hours=[14, 12]),
                explanation="bad order",
            )
        ]
        with pytest.raises(GuardrailError, match="ascending order"):
            validate_directives(directives, hours, note_count=1)

    def test_rejects_duplicate_hours(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.NO_CHARGE_WINDOW,
                structured_adjustment=StructuredAdjustment(hours=[12, 12]),
                explanation="dup",
            )
        ]
        with pytest.raises(GuardrailError, match="must be unique"):
            validate_directives(directives, hours, note_count=1)

    def test_wrong_count_raises(self) -> None:
        hours = _make_hours()
        directives = []
        with pytest.raises(GuardrailError, match="Expected 1 directives"):
            validate_directives(directives, hours, note_count=1)

    def test_note_index_correction(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=5,  # wrong index
                applies=False,
                directive_type=DirectiveType.NO_OP,
                structured_adjustment=None,
                explanation="fix",
            )
        ]
        result = validate_directives(directives, hours, note_count=1)
        assert result[0].note_index == 0

    def test_non_noop_with_applies_false_corrected(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=False,  # wrong
                directive_type=DirectiveType.NO_CHARGE_WINDOW,
                structured_adjustment=StructuredAdjustment(hours=[12]),
                explanation="fix",
            )
        ]
        result = validate_directives(directives, hours, note_count=1)
        assert result[0].applies is True

    def test_max_grid_window_valid(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.MAX_GRID_WINDOW,
                structured_adjustment=StructuredAdjustment(
                    hours=[18, 19, 20], max_grid_kwh=155
                ),
                explanation="feeder cap",
            )
        ]
        result = validate_directives(directives, hours, note_count=1)
        assert result[0].directive_type == DirectiveType.MAX_GRID_WINDOW

    def test_minimum_battery_reserve_valid(self) -> None:
        hours = _make_hours()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.MINIMUM_BATTERY_RESERVE,
                structured_adjustment=StructuredAdjustment(
                    hours=[18, 19, 20], minimum_energy_kwh=100
                ),
                explanation="emergency reserve",
            )
        ]
        result = validate_directives(directives, hours, note_count=1)
        assert result[0].directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE
