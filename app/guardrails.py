"""Deterministic guardrails for LLM directive interpretation.

These validators run **before** any directive is applied to the optimisation
model.  Invalid output is corrected or rejected so that downstream code only
sees well-formed, consistent directives.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from .models import (
    DirectiveInterpretation,
    DirectiveType,
    HourEntry,
    StructuredAdjustment,
)

logger = logging.getLogger(__name__)

SUPPORTED_DIRECTIVE_TYPES: set[str] = {dt.value for dt in DirectiveType}


class GuardrailError(Exception):
    """Raised when guardrails detect an irrecoverable problem."""


# ---------------------------------------------------------------------------
# Per-directive validation helpers
# ---------------------------------------------------------------------------


def _validate_solar_reduction(
    adj: StructuredAdjustment,
    note_idx: int,
) -> None:
    if adj.hours is None or not adj.hours:
        raise GuardrailError(
            f"note {note_idx}: solar_reduction requires 'hours'"
        )
    if adj.factor is None or not (0.0 <= adj.factor <= 1.0):
        raise GuardrailError(
            f"note {note_idx}: solar_reduction factor must be in [0, 1]"
        )


def _validate_minimum_battery_reserve(
    adj: StructuredAdjustment,
    note_idx: int,
) -> None:
    if adj.hours is None or not adj.hours:
        raise GuardrailError(
            f"note {note_idx}: minimum_battery_reserve requires 'hours'"
        )
    if adj.minimum_energy_kwh is None or adj.minimum_energy_kwh < 0:
        raise GuardrailError(
            f"note {note_idx}: minimum_battery_reserve requires "
            "non-negative 'minimum_energy_kwh'"
        )


def _validate_no_charge_window(
    adj: StructuredAdjustment,
    note_idx: int,
) -> None:
    if adj.hours is None or not adj.hours:
        raise GuardrailError(
            f"note {note_idx}: no_charge_window requires 'hours'"
        )


def _validate_no_discharge_window(
    adj: StructuredAdjustment,
    note_idx: int,
) -> None:
    if adj.hours is None or not adj.hours:
        raise GuardrailError(
            f"note {note_idx}: no_discharge_window requires 'hours'"
        )


def _validate_max_grid_window(
    adj: StructuredAdjustment,
    note_idx: int,
) -> None:
    if adj.hours is None or not adj.hours:
        raise GuardrailError(
            f"note {note_idx}: max_grid_window requires 'hours'"
        )
    if adj.max_grid_kwh is None or adj.max_grid_kwh < 0:
        raise GuardrailError(
            f"note {note_idx}: max_grid_window requires "
            "non-negative 'max_grid_kwh'"
        )


_VALIDATORS = {
    DirectiveType.SOLAR_REDUCTION: _validate_solar_reduction,
    DirectiveType.MINIMUM_BATTERY_RESERVE: _validate_minimum_battery_reserve,
    DirectiveType.NO_CHARGE_WINDOW: _validate_no_charge_window,
    DirectiveType.NO_DISCHARGE_WINDOW: _validate_no_discharge_window,
    DirectiveType.MAX_GRID_WINDOW: _validate_max_grid_window,
}


# ---------------------------------------------------------------------------
# Hours validation
# ---------------------------------------------------------------------------


def _validate_hours(hours: Sequence[int], note_idx: int) -> None:
    if not hours:
        raise GuardrailError(f"note {note_idx}: hours list is empty")
    if len(hours) != len(set(hours)):
        raise GuardrailError(f"note {note_idx}: hours must be unique")
    if any(h < 0 or h > 23 for h in hours):
        raise GuardrailError(
            f"note {note_idx}: hours must be integers 0-23"
        )
    if hours != sorted(hours):
        raise GuardrailError(
            f"note {note_idx}: hours must be in ascending order"
        )


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_directives(
    directives: Sequence[DirectiveInterpretation],
    hours: list[HourEntry],
    note_count: int,
) -> list[DirectiveInterpretation]:
    """Validate and normalise a list of directive interpretations.

    Returns a (possibly corrected) list that is safe for downstream use.
    Raises ``GuardrailError`` on irrecoverable problems.
    """
    if len(directives) != note_count:
        raise GuardrailError(
            f"Expected {note_count} directives, got {len(directives)}"
        )

    validated: list[DirectiveInterpretation] = []

    for idx, d in enumerate(directives):
        # Ensure note_index matches position
        if d.note_index != idx:
            logger.warning(
                "note_index mismatch: expected %d, got %d — correcting",
                idx,
                d.note_index,
            )
            d = d.model_copy(update={"note_index": idx})

        # Validate directive type
        if d.directive_type not in SUPPORTED_DIRECTIVE_TYPES:
            logger.warning(
                "Unsupported directive_type '%s' at note %d — "
                "downgrading to no_op",
                d.directive_type,
                idx,
            )
            d = DirectiveInterpretation(
                note_index=idx,
                applies=False,
                directive_type=DirectiveType.NO_OP,
                structured_adjustment=None,
                explanation=(
                    f"Unsupported directive type '{d.directive_type}' "
                    "was downgraded to no_op"
                ),
            )
            validated.append(d)
            continue

        # no_op must have applies=false and null adjustment
        if d.directive_type == DirectiveType.NO_OP:
            if d.applies:
                logger.warning(
                    "note %d: no_op with applies=true — correcting",
                    idx,
                )
            d = d.model_copy(
                update={"applies": False, "structured_adjustment": None}
            )
            validated.append(d)
            continue

        # All other directives must have applies=true
        if not d.applies:
            logger.warning(
                "note %d: non-no_op directive with applies=false "
                "— correcting to true",
                idx,
            )
            d = d.model_copy(update={"applies": True})

        # Validate structured_adjustment shape
        if d.structured_adjustment is None:
            raise GuardrailError(
                f"note {idx}: non-no_op directive requires "
                "structured_adjustment"
            )

        # Validate hours array
        if d.structured_adjustment.hours is not None:
            _validate_hours(d.structured_adjustment.hours, idx)

        # Validate directive-specific fields
        validator = _VALIDATORS.get(d.directive_type)
        if validator:
            validator(d.structured_adjustment, idx)

        # Validate reserve does not exceed battery capacity
        if (
            d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE
            and d.structured_adjustment.minimum_energy_kwh is not None
        ):
            max(h.demand_kwh for h in hours)  # rough bound
            # Exact battery capacity comes from request — we validate later
            # in the optimizer where we have full context.

        validated.append(d)

    return validated
