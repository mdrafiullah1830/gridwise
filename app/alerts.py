"""Constraint violation detection for GridWise schedules."""

from __future__ import annotations

from .models import (
    BatterySpec,
    DirectiveInterpretation,
    DirectiveType,
    HourEntry,
    HourlyPlanEntry,
    Violation,
    ViolationSeverity,
)


def detect_violations(
    plan: list[HourlyPlanEntry],
    hours: list[HourEntry],
    battery: BatterySpec,
    directives: list[DirectiveInterpretation],
) -> list[Violation]:
    """Scan a completed schedule for constraint violations."""
    violations: list[Violation] = []

    # Collect directive constraints
    no_charge_hours: set[int] = set()
    no_discharge_hours: set[int] = set()
    max_grid_caps: dict[int, float] = {}
    min_reserves: dict[int, float] = {}

    for d in directives:
        if not d.applies or d.structured_adjustment is None:
            continue
        adj = d.structured_adjustment
        if d.directive_type == DirectiveType.NO_CHARGE_WINDOW and adj.hours:
            no_charge_hours.update(adj.hours)
        elif d.directive_type == DirectiveType.NO_DISCHARGE_WINDOW and adj.hours:
            no_discharge_hours.update(adj.hours)
        elif d.directive_type == DirectiveType.MAX_GRID_WINDOW and adj.hours and adj.max_grid_kwh is not None:
            for hr in adj.hours:
                max_grid_caps[hr] = min(max_grid_caps.get(hr, float("inf")), adj.max_grid_kwh)
        elif d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE and adj.hours and adj.minimum_energy_kwh is not None:
            for hr in adj.hours:
                min_reserves[hr] = max(min_reserves.get(hr, 0), adj.minimum_energy_kwh)

    for h in plan:
        hr = h.hour

        # 1. Battery below minimum reserve
        effective_min = min_reserves.get(hr, battery.minimum_energy_kwh)
        if h.battery_energy_after_kwh < effective_min - 0.01:
            violations.append(Violation(
                hour=hr,
                violation_type="battery_below_reserve",
                actual_value=h.battery_energy_after_kwh,
                expected_value=effective_min,
                severity=ViolationSeverity.HIGH,
                message=f"H{hr:02d}: Battery SOC {h.battery_energy_after_kwh:.1f} kWh below minimum reserve {effective_min:.1f} kWh",
            ))

        # 2. Battery exceeds capacity
        if h.battery_energy_after_kwh > battery.capacity_kwh + 0.01:
            violations.append(Violation(
                hour=hr,
                violation_type="battery_over_capacity",
                actual_value=h.battery_energy_after_kwh,
                expected_value=battery.capacity_kwh,
                severity=ViolationSeverity.HIGH,
                message=f"H{hr:02d}: Battery SOC {h.battery_energy_after_kwh:.1f} kWh exceeds capacity {battery.capacity_kwh:.1f} kWh",
            ))

        # 3. Grid exceeds cap
        if hr in max_grid_caps and h.grid_kwh > max_grid_caps[hr] + 0.01:
            violations.append(Violation(
                hour=hr,
                violation_type="grid_exceeds_cap",
                actual_value=h.grid_kwh,
                expected_value=max_grid_caps[hr],
                severity=ViolationSeverity.MEDIUM,
                message=f"H{hr:02d}: Grid import {h.grid_kwh:.1f} kWh exceeds cap {max_grid_caps[hr]:.1f} kWh",
            ))

        # 4. Charging during no-charge window
        if hr in no_charge_hours and h.battery_action.value == "charge" and h.battery_kwh > 0.01:
            violations.append(Violation(
                hour=hr,
                violation_type="charge_in_no_charge_window",
                actual_value=h.battery_kwh,
                expected_value=0.0,
                severity=ViolationSeverity.HIGH,
                message=f"H{hr:02d}: Charging {h.battery_kwh:.1f} kWh during no-charge window",
            ))

        # 5. Discharging during no-discharge window
        if hr in no_discharge_hours and h.battery_action.value == "discharge" and h.battery_kwh > 0.01:
            violations.append(Violation(
                hour=hr,
                violation_type="discharge_in_no_discharge_window",
                actual_value=h.battery_kwh,
                expected_value=0.0,
                severity=ViolationSeverity.HIGH,
                message=f"H{hr:02d}: Discharging {h.battery_kwh:.1f} kWh during no-discharge window",
            ))

        # 6. Solar usage exceeds available solar
        avail_solar = hours[hr].solar_kwh
        # Apply solar reduction directives
        for d in directives:
            if (
                d.directive_type == DirectiveType.SOLAR_REDUCTION
                and d.applies
                and d.structured_adjustment
                and d.structured_adjustment.hours
                and d.structured_adjustment.factor is not None
                and hr in d.structured_adjustment.hours
            ):
                avail_solar *= d.structured_adjustment.factor
        if h.solar_used_kwh > avail_solar + 0.01:
            violations.append(Violation(
                hour=hr,
                violation_type="solar_over_available",
                actual_value=h.solar_used_kwh,
                expected_value=avail_solar,
                severity=ViolationSeverity.MEDIUM,
                message=f"H{hr:02d}: Solar used {h.solar_used_kwh:.1f} kWh exceeds available {avail_solar:.1f} kWh",
            ))

        # 7. Energy balance check
        expected_grid = h.grid_kwh + h.solar_used_kwh
        actual_demand = hours[hr].demand_kwh
        if h.battery_action.value == "charge":
            expected_demand = actual_demand + h.battery_kwh
        elif h.battery_action.value == "discharge":
            expected_demand = actual_demand - h.battery_kwh
        else:
            expected_demand = actual_demand
        if abs(expected_grid - expected_demand) > 0.1:
            violations.append(Violation(
                hour=hr,
                violation_type="energy_balance_mismatch",
                actual_value=expected_grid,
                expected_value=expected_demand,
                severity=ViolationSeverity.LOW,
                message=f"H{hr:02d}: Energy balance mismatch — supply {expected_grid:.1f} vs demand {expected_demand:.1f}",
            ))

    return violations


def violations_summary(violations: list[Violation]) -> dict:
    """Return summary statistics for violations."""
    high = sum(1 for v in violations if v.severity == ViolationSeverity.HIGH)
    medium = sum(1 for v in violations if v.severity == ViolationSeverity.MEDIUM)
    low = sum(1 for v in violations if v.severity == ViolationSeverity.LOW)
    return {
        "total": len(violations),
        "high": high,
        "medium": medium,
        "low": low,
        "hours_affected": sorted({v.hour for v in violations}),
        "is_clean": len(violations) == 0,
    }
