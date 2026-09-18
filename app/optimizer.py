"""Mixed-Integer Linear Program (MILP) optimizer for 24-hour energy scheduling.

Uses PuLP to minimise total grid electricity cost while respecting:
- Hourly energy balance
- Solar availability (with reduction directives)
- Battery state-of-charge bounds and rate limits
- Operator-directive constraints (charge/discharge windows, reserve, grid cap)
- End-of-day battery neutrality
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import pulp

from .models import (
    BatteryAction,
    BatterySpec,
    DirectiveInterpretation,
    DirectiveType,
    HourEntry,
    HourlyPlanEntry,
    OptimizeResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Effective-solar calculation
# ---------------------------------------------------------------------------


def _effective_solar(
    hours: list[HourEntry],
    directives: Sequence[DirectiveInterpretation],
) -> list[float]:
    """Compute effective solar for each hour after applying reductions."""
    solar = [h.solar_kwh for h in hours]
    for d in directives:
        if (
            d.directive_type == DirectiveType.SOLAR_REDUCTION
            and d.applies
            and d.structured_adjustment is not None
            and d.structured_adjustment.hours is not None
            and d.structured_adjustment.factor is not None
        ):
            for hr in d.structured_adjustment.hours:
                if 0 <= hr < 24:
                    solar[hr] *= d.structured_adjustment.factor
    return solar


# ---------------------------------------------------------------------------
# Directive helpers
# ---------------------------------------------------------------------------


def _no_charge_hours(
    directives: Sequence[DirectiveInterpretation],
) -> set[int]:
    hrs: set[int] = set()
    for d in directives:
        if (
            d.directive_type == DirectiveType.NO_CHARGE_WINDOW
            and d.applies
            and d.structured_adjustment is not None
            and d.structured_adjustment.hours is not None
        ):
            hrs.update(d.structured_adjustment.hours)
    return hrs


def _no_discharge_hours(
    directives: Sequence[DirectiveInterpretation],
) -> set[int]:
    hrs: set[int] = set()
    for d in directives:
        if (
            d.directive_type == DirectiveType.NO_DISCHARGE_WINDOW
            and d.applies
            and d.structured_adjustment is not None
            and d.structured_adjustment.hours is not None
        ):
            hrs.update(d.structured_adjustment.hours)
    return hrs


def _min_reserve_map(
    directives: Sequence[DirectiveInterpretation],
    base_min: float,
) -> dict[int, float]:
    """Return per-hour minimum reserve (at least base_min)."""
    m: dict[int, float] = {}
    for d in directives:
        if (
            d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE
            and d.applies
            and d.structured_adjustment is not None
            and d.structured_adjustment.hours is not None
            and d.structured_adjustment.minimum_energy_kwh is not None
        ):
            for hr in d.structured_adjustment.hours:
                m[hr] = max(m.get(hr, base_min), d.structured_adjustment.minimum_energy_kwh)
    # Fill missing hours with base_min
    for hr in range(24):
        m.setdefault(hr, base_min)
    return m


def _max_grid_map(
    directives: Sequence[DirectiveInterpretation],
) -> dict[int, float]:
    """Return per-hour grid cap (inf if no cap)."""
    m: dict[int, float] = {}
    for d in directives:
        if (
            d.directive_type == DirectiveType.MAX_GRID_WINDOW
            and d.applies
            and d.structured_adjustment is not None
            and d.structured_adjustment.hours is not None
            and d.structured_adjustment.max_grid_kwh is not None
        ):
            for hr in d.structured_adjustment.hours:
                m[hr] = min(m.get(hr, float("inf")), d.structured_adjustment.max_grid_kwh)
    return m


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------


def optimize(
    hours: list[HourEntry],
    battery: BatterySpec,
    directives: Sequence[DirectiveInterpretation],
    scenario_id: str,
) -> OptimizeResponse:
    """Build and solve the MILP, return the optimal schedule."""

    eff_solar = _effective_solar(hours, directives)
    no_chg = _no_charge_hours(directives)
    no_dch = _no_discharge_hours(directives)
    min_res = _min_reserve_map(directives, battery.minimum_energy_kwh)
    max_grid = _max_grid_map(directives)

    demand = [h.demand_kwh for h in hours]
    tariff = [h.tariff_bdt_per_kwh for h in hours]

    prob = pulp.LpProblem("GridWise", pulp.LpMinimize)

    # ---- Decision variables ----
    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0) for h in range(24)]
    solar_used = [pulp.LpVariable(f"solar_{h}", lowBound=0) for h in range(24)]
    charge = [pulp.LpVariable(f"charge_{h}", lowBound=0) for h in range(24)]
    discharge = [pulp.LpVariable(f"discharge_{h}", lowBound=0) for h in range(24)]
    energy = [pulp.LpVariable(f"energy_{h}", lowBound=0) for h in range(24)]
    is_ch = [pulp.LpVariable(f"is_ch_{h}", cat="Binary") for h in range(24)]
    is_dch = [pulp.LpVariable(f"is_dch_{h}", cat="Binary") for h in range(24)]

    # ---- Objective: minimise total grid cost ----
    prob += pulp.lpSum(grid[h] * tariff[h] for h in range(24))

    for h in range(24):
        # Energy balance
        prob += (
            grid[h] + solar_used[h] + discharge[h]
            == demand[h] + charge[h],
            f"balance_{h}",
        )

        # Solar usage <= effective solar
        prob += solar_used[h] <= eff_solar[h], f"solar_cap_{h}"

        # Battery state transition
        if h == 0:
            prob += (
                energy[h] == battery.initial_energy_kwh + charge[h] - discharge[h],
                f"state_{h}",
            )
        else:
            prob += (
                energy[h] == energy[h - 1] + charge[h] - discharge[h],
                f"state_{h}",
            )

        # Battery bounds (using per-hour minimum reserve)
        prob += energy[h] >= min_res[h], f"min_res_{h}"
        prob += energy[h] <= battery.capacity_kwh, f"max_cap_{h}"

        # Charge/discharge rate limits
        prob += charge[h] <= battery.max_charge_kwh_per_hour * is_ch[h], f"rate_ch_{h}"
        prob += discharge[h] <= battery.max_discharge_kwh_per_hour * is_dch[h], f"rate_dch_{h}"

        # Mutual exclusion
        prob += is_ch[h] + is_dch[h] <= 1, f"mutex_{h}"

        # No-charge window
        if h in no_chg:
            prob += charge[h] == 0, f"no_charge_{h}"

        # No-discharge window
        if h in no_dch:
            prob += discharge[h] == 0, f"no_discharge_{h}"

        # Max grid cap
        if h in max_grid:
            prob += grid[h] <= max_grid[h], f"max_grid_{h}"

    # End-of-day neutrality
    prob += (
        energy[23] == battery.initial_energy_kwh,
        "eod_neutrality",
    )

    # ---- Solve ----
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=30)
    status = prob.solve(solver)

    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(
            f"Optimizer status: {pulp.LpStatus[status]}"
        )

    # ---- Extract results ----
    hourly_plan: list[HourlyPlanEntry] = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for h in range(24):
        g_val = float(grid[h].varValue or 0)
        s_val = float(solar_used[h].varValue or 0)
        c_val = float(charge[h].varValue or 0)
        d_val = float(discharge[h].varValue or 0)
        e_val = float(energy[h].varValue or 0)

        # Determine action
        if c_val > 0.01:
            action = BatteryAction.CHARGE
            batt_kwh = c_val
        elif d_val > 0.01:
            action = BatteryAction.DISCHARGE
            batt_kwh = d_val
        else:
            action = BatteryAction.IDLE
            batt_kwh = 0.0

        hourly_plan.append(
            HourlyPlanEntry(
                hour=h,
                grid_kwh=round(g_val, 4),
                solar_used_kwh=round(s_val, 4),
                battery_action=action,
                battery_kwh=round(batt_kwh, 4),
                battery_energy_after_kwh=round(e_val, 4),
            )
        )

        total_grid += g_val
        total_cost += g_val * tariff[h]
        peak_grid = max(peak_grid, g_val)

    # Build directive interpretations for response

    return OptimizeResponse(
        scenario_id=scenario_id,
        directive_interpretation=list(directives),
        hourly_plan=hourly_plan,
        total_grid_kwh=round(total_grid, 2),
        total_cost_bdt=round(total_cost, 2),
        peak_grid_kwh=round(peak_grid, 2),
        plan_summary=_build_summary(directives, eff_solar, no_chg, no_dch),
    )


def _build_summary(
    directives: Sequence[DirectiveInterpretation],
    eff_solar: list[float],
    no_chg: set[int],
    no_dch: set[int],
) -> str:
    """Build a short human-readable plan summary."""
    parts: list[str] = []

    applied = [d for d in directives if d.applies and d.directive_type != DirectiveType.NO_OP]
    distractors = [d for d in directives if d.directive_type == DirectiveType.NO_OP]

    if not applied:
        parts.append("No active operator directives; optimising against the base scenario.")
    else:
        for d in applied:
            if d.directive_type == DirectiveType.SOLAR_REDUCTION:
                parts.append(
                    f"Solar reduction applied for hours "
                    f"{d.structured_adjustment.hours} (factor "
                    f"{d.structured_adjustment.factor})."
                )
            elif d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE:
                parts.append(
                    f"Emergency battery reserve of "
                    f"{d.structured_adjustment.minimum_energy_kwh} kWh "
                    f"maintained for hours {d.structured_adjustment.hours}."
                )
            elif d.directive_type == DirectiveType.NO_CHARGE_WINDOW:
                parts.append(
                    f"Battery charging disabled during hours "
                    f"{d.structured_adjustment.hours}."
                )
            elif d.directive_type == DirectiveType.NO_DISCHARGE_WINDOW:
                parts.append(
                    f"Battery discharging disabled during hours "
                    f"{d.structured_adjustment.hours}."
                )
            elif d.directive_type == DirectiveType.MAX_GRID_WINDOW:
                parts.append(
                    f"Grid import capped at "
                    f"{d.structured_adjustment.max_grid_kwh} kWh "
                    f"during hours {d.structured_adjustment.hours}."
                )

    if distractors:
        parts.append(
            f"{len(distractors)} distractor note(s) identified and ignored."
        )

    parts.append("Schedule optimised to minimise total grid electricity cost.")

    return " ".join(parts)
