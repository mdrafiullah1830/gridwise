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
