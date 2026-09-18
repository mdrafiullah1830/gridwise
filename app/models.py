"""Pydantic models for the GridWise API request / response schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DirectiveType(str, Enum):
    SOLAR_REDUCTION = "solar_reduction"
    MINIMUM_BATTERY_RESERVE = "minimum_battery_reserve"
    NO_CHARGE_WINDOW = "no_charge_window"
    NO_DISCHARGE_WINDOW = "no_discharge_window"
    MAX_GRID_WINDOW = "max_grid_window"
    NO_OP = "no_op"


class BatteryAction(str, Enum):
    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"


class ViolationSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class HourEntry(BaseModel):
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)


class BatterySpec(BaseModel):
    capacity_kwh: float = Field(gt=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(gt=0)
    max_discharge_kwh_per_hour: float = Field(gt=0)

    @model_validator(mode="after")
    def _validate_battery(self) -> BatterySpec:
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError(
                "initial_energy_kwh cannot exceed capacity_kwh"
            )
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError(
                "minimum_energy_kwh cannot exceed capacity_kwh"
            )
        return self


class OptimizeRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourEntry] = Field(min_length=24, max_length=24)
    battery: BatterySpec

    @model_validator(mode="after")
    def _validate_hours(self) -> OptimizeRequest:
        hours_seen = {h.hour for h in self.hours}
        if hours_seen != set(range(24)):
            raise ValueError("hours must contain exactly entries 0 through 23")
        return self


# ---------------------------------------------------------------------------
# Directive interpretation models
# ---------------------------------------------------------------------------

class StructuredAdjustment(BaseModel):
    """Polymorphic adjustment — only the relevant fields are set."""

    hours: list[int] | None = None
    factor: float | None = None
    minimum_energy_kwh: float | None = None
    max_grid_kwh: float | None = None


class DirectiveInterpretation(BaseModel):
    note_index: int = Field(ge=0)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: StructuredAdjustment | None = None
    explanation: str = ""


# ---------------------------------------------------------------------------
# Hourly plan models
# ---------------------------------------------------------------------------

class HourlyPlanEntry(BaseModel):
    hour: int = Field(ge=0, le=23)
    grid_kwh: float = Field(ge=0)
    solar_used_kwh: float = Field(ge=0)
    battery_action: BatteryAction
    battery_kwh: float = Field(ge=0)
    battery_energy_after_kwh: float


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str
    solver_status: str = "Optimal"
    solve_time_ms: float = 0.0
    objective_value: float = 0.0
    # v4.0 features
    violations: list[Violation] = Field(default_factory=list)
    violation_summary: dict = Field(default_factory=dict)
    degradation_cost_bdt: float = 0.0
    total_cycles: float = 0.0
    tariff_tier_label: str = "flat"


class BaselineResponse(BaseModel):
    """Response from POST /optimize-energy/baseline.

    Compares the directive-driven schedule against the no-directive baseline.
    """
    scenario_id: str
    baseline_cost_bdt: float
    optimised_cost_bdt: float
    savings_bdt: float
    savings_pct: float
    baseline_grid_kwh: float
    optimised_grid_kwh: float
    baseline_peak_grid_kwh: float
    optimised_peak_grid_kwh: float
    baseline_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    optimised_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    solver_status: str = "Optimal"
    solve_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# Comparison models
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    scenarios: list[OptimizeRequest] = Field(min_length=2, max_length=5)


class ScenarioSummary(BaseModel):
    scenario_id: str
    total_cost_bdt: float
    total_grid_kwh: float
    peak_grid_kwh: float
    savings_bdt: float = 0.0
    savings_pct: float = 0.0
    hourly_plan: list[HourlyPlanEntry]
    directive_count: int = 0


class CompareResponse(BaseModel):
    scenarios: list[ScenarioSummary]
    best_scenario_id: str
    cost_difference_bdt: float


# ---------------------------------------------------------------------------
# What-if models
# ---------------------------------------------------------------------------

class WhatIfRequest(BaseModel):
    scenario_id: str = "WHAT-IF"
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourEntry] = Field(min_length=24, max_length=24)
    battery: BatterySpec
    param: str = Field(min_length=1)
    values: list[float] = Field(min_length=2, max_length=10)


class WhatIfPoint(BaseModel):
    value: float
    total_cost_bdt: float
    total_grid_kwh: float
    peak_grid_kwh: float


class WhatIfResponse(BaseModel):
    scenario_id: str
    param: str
    points: list[WhatIfPoint]
    baseline_cost_bdt: float


# ---------------------------------------------------------------------------
# Carbon models
# ---------------------------------------------------------------------------

class CarbonOptimizeRequest(OptimizeRequest):
    carbon_factor_kg_per_kwh: float = Field(default=0.5, ge=0)
    cost_weight: float = Field(default=0.7, ge=0, le=1)
    carbon_weight: float = Field(default=0.3, ge=0, le=1)


class CarbonOptimizeResponse(OptimizeResponse):
    total_carbon_kg: float = 0.0
    baseline_carbon_kg: float = 0.0
    carbon_savings_kg: float = 0.0
    weighted_objective: float = 0.0


# ---------------------------------------------------------------------------
# Template models
# ---------------------------------------------------------------------------

class ScenarioTemplate(BaseModel):
    id: str
    name: str
    description: str
    notes: list[str]
    battery: BatterySpec
    hours: list[HourEntry]


# ---------------------------------------------------------------------------
# Violation model (v4.0)
# ---------------------------------------------------------------------------

class Violation(BaseModel):
    hour: int = Field(ge=0, le=23)
    violation_type: str
    actual_value: float
    expected_value: float
    severity: ViolationSeverity
    message: str


# ---------------------------------------------------------------------------
# Tariff tier model (v4.0)
# ---------------------------------------------------------------------------

class TariffTier(BaseModel):
    name: str
    hours: list[int] = Field(min_length=1)
    multiplier: float = Field(default=1.0, gt=0)


class TariffConfig(BaseModel):
    enabled: bool = False
    tiers: list[TariffTier] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Battery degradation model (v4.0)
# ---------------------------------------------------------------------------

class BatteryDegradation(BaseModel):
    enabled: bool = False
    cost_per_cycle_bdt: float = Field(default=0.0, ge=0)
    max_cycles: int = Field(default=3000, gt=0)


# ---------------------------------------------------------------------------
# Cost trend model (v4.0)
# ---------------------------------------------------------------------------

class CostTrendPoint(BaseModel):
    run_id: int
    scenario_id: str
    total_cost_bdt: float
    total_grid_kwh: float
    total_carbon_kg: float | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Carbon stats model (v4.0)
# ---------------------------------------------------------------------------

class CarbonStats(BaseModel):
    total_runs: int = 0
    total_carbon_kg: float = 0.0
    total_carbon_saved_kg: float = 0.0
    avg_carbon_kg: float = 0.0
    best_run_id: int | None = None
    best_carbon_saving_kg: float = 0.0
