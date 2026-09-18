"""Tests for the MILP optimizer module."""

from __future__ import annotations

from app.models import (
    BatterySpec,
    DirectiveInterpretation,
    DirectiveType,
    HourEntry,
    StructuredAdjustment,
)
from app.optimizer import optimize


def _make_hours() -> list[HourEntry]:
    """Standard 24-hour scenario matching SAMPLE-01."""
    demand = [
        90, 85, 80, 80, 85, 95, 110, 130, 150, 165,
        175, 180, 185, 180, 170, 165, 170, 185, 205, 215,
        205, 175, 135, 105,
    ]
    solar = [
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
        HourEntry(hour=h, demand_kwh=demand[h], solar_kwh=solar[h], tariff_bdt_per_kwh=tariff[h])
        for h in range(24)
    ]


def _make_battery() -> BatterySpec:
    return BatterySpec(
        capacity_kwh=220,
        initial_energy_kwh=110,
        minimum_energy_kwh=40,
        max_charge_kwh_per_hour=50,
        max_discharge_kwh_per_hour=50,
    )


class TestOptimizer:
    """The optimizer should produce valid, cost-minimised schedules."""

    def test_no_directives(self) -> None:
        hours = _make_hours()
        battery = _make_battery()
        result = optimize(hours, battery, [], scenario_id="TEST-00")

        assert result.scenario_id == "TEST-00"
        assert len(result.hourly_plan) == 24

        # Check energy balance for every hour
        for entry in result.hourly_plan:
            h = entry.hour
            demand = hours[h].demand_kwh
            balance = (
                entry.grid_kwh
                + entry.solar_used_kwh
                + (entry.battery_kwh if entry.battery_action.value == "discharge" else 0)
            )
            supply = demand + (
                entry.battery_kwh if entry.battery_action.value == "charge" else 0
            )
            assert abs(balance - supply) < 0.01, f"balance fail at hour {h}"

        # End-of-day neutrality
        assert abs(
            result.hourly_plan[23].battery_energy_after_kwh
            - battery.initial_energy_kwh
        ) < 0.01

        # Totals
        assert result.total_grid_kwh > 0
        assert result.total_cost_bdt > 0
        assert result.peak_grid_kwh > 0

    def test_solar_reduction(self) -> None:
        hours = _make_hours()
        battery = _make_battery()
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
        result = optimize(hours, battery, directives, scenario_id="TEST-01")

        # Hour 12: effective solar = 180 * 0.25 = 45
        h12 = result.hourly_plan[12]
        assert h12.solar_used_kwh <= 45.01

        # Hour 13: effective solar = 170 * 0.25 = 42.5
        h13 = result.hourly_plan[13]
        assert h13.solar_used_kwh <= 42.51

    def test_no_charge_window(self) -> None:
        hours = _make_hours()
        battery = _make_battery()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.NO_CHARGE_WINDOW,
                structured_adjustment=StructuredAdjustment(hours=[2, 3, 4]),
                explanation="maintenance",
            )
        ]
        result = optimize(hours, battery, directives, scenario_id="TEST-02")

        for hr in [2, 3, 4]:
            entry = result.hourly_plan[hr]
            assert entry.battery_action.value != "charge", (
                f"charge at hour {hr} should be forbidden"
            )

    def test_no_discharge_window(self) -> None:
        hours = _make_hours()
        battery = _make_battery()
        directives = [
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type=DirectiveType.NO_DISCHARGE_WINDOW,
                structured_adjustment=StructuredAdjustment(hours=[18, 19]),
                explanation="protection test",
            )
        ]
        result = optimize(hours, battery, directives, scenario_id="TEST-03")

        for hr in [18, 19]:
            entry = result.hourly_plan[hr]
            assert entry.battery_action.value != "discharge", (
                f"discharge at hour {hr} should be forbidden"
            )

    def test_minimum_battery_reserve(self) -> None:
        hours = _make_hours()
        battery = _make_battery()
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
        result = optimize(hours, battery, directives, scenario_id="TEST-04")

        for hr in [18, 19, 20]:
            entry = result.hourly_plan[hr]
            assert entry.battery_energy_after_kwh >= 99.99, (
                f"reserve violated at hour {hr}: {entry.battery_energy_after_kwh}"
            )

    def test_max_grid_window(self) -> None:
        hours = _make_hours()
        # Use a larger battery (matching SAMPLE-05) so the grid cap is feasible
        battery = BatterySpec(
            capacity_kwh=240,
            initial_energy_kwh=120,
            minimum_energy_kwh=30,
            max_charge_kwh_per_hour=60,
            max_discharge_kwh_per_hour=60,
        )
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
        result = optimize(hours, battery, directives, scenario_id="TEST-05")

        for hr in [18, 19, 20]:
            entry = result.hourly_plan[hr]
            assert entry.grid_kwh <= 155.01, (
                f"grid cap violated at hour {hr}: {entry.grid_kwh}"
            )

    def test_battery_neutrality(self) -> None:
        hours = _make_hours()
        battery = _make_battery()
        result = optimize(hours, battery, [], scenario_id="TEST-NEUT")
        initial = battery.initial_energy_kwh
        final = result.hourly_plan[23].battery_energy_after_kwh
        assert abs(final - initial) < 0.01
