"""Tests for v4.0 features: alerts, tariff tiers, degradation."""

from __future__ import annotations

from app.alerts import detect_violations, violations_summary
from app.models import (
    BatteryDegradation,
    BatterySpec,
    DirectiveInterpretation,
    DirectiveType,
    HourEntry,
    StructuredAdjustment,
    TariffConfig,
    TariffTier,
    ViolationSeverity,
)
from app.optimizer import _apply_tariff_tiers, _compute_degradation_cost, optimize

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_hours():
    return [
        HourEntry(hour=h, demand_kwh=150, solar_kwh=max(0, (h - 5) * 30) if 6 <= h <= 18 else 0, tariff_bdt_per_kwh=5.0)
        for h in range(24)
    ]


def _make_battery():
    return BatterySpec(capacity_kwh=220, initial_energy_kwh=110, minimum_energy_kwh=40,
                       max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50)


def _make_plan(hours, battery, directives=None):
    """Run optimizer and return the hourly plan."""
    resp = optimize(hours=hours, battery=battery, directives=directives or [],
                    scenario_id="TEST")
    return resp.hourly_plan, resp


# ---------------------------------------------------------------------------
# Alert tests
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_clean_schedule_no_violations(self):
        hours = _make_hours()
        battery = _make_battery()
        plan, _ = _make_plan(hours, battery)
        violations = detect_violations(plan, hours, battery, [])
        summary = violations_summary(violations)
        assert summary["is_clean"] is True
        assert summary["total"] == 0

    def test_charge_in_no_charge_window(self):
        hours = _make_hours()
        battery = _make_battery()
        directives = [DirectiveInterpretation(
            note_index=0, applies=True,
            directive_type=DirectiveType.NO_CHARGE_WINDOW,
            structured_adjustment=StructuredAdjustment(hours=[10, 11]),
            explanation="No charge during peak",
        )]
        plan, _ = _make_plan(hours, battery, directives)
        # Check if any charging happens at hour 10 or 11
        violations = detect_violations(plan, hours, battery, directives)
        # The optimizer should respect no-charge, but test the detector
        charge_violations = [v for v in violations if v.violation_type == "charge_in_no_charge_window"]
        # Should be empty if optimizer respects constraint
        assert len(charge_violations) == 0

    def test_violation_severity_enum(self):
        assert ViolationSeverity.HIGH.value == "high"
        assert ViolationSeverity.MEDIUM.value == "medium"
        assert ViolationSeverity.LOW.value == "low"


# ---------------------------------------------------------------------------
# Tariff tier tests
# ---------------------------------------------------------------------------

class TestTariffTiers:
    def test_flat_tariff(self):
        base = [5.0] * 24
        config = TariffConfig(enabled=False)
        result, label = _apply_tariff_tiers(base, config)
        assert result == base
        assert label == "flat"

    def test_peak_multiplier(self):
        base = [5.0] * 24
        config = TariffConfig(enabled=True, tiers=[
            TariffTier(name="peak", hours=[18, 19, 20], multiplier=2.0),
        ])
        result, _label = _apply_tariff_tiers(base, config)
        assert result[18] == 10.0
        assert result[19] == 10.0
        assert result[0] == 5.0  # unchanged

    def test_multiple_tiers(self):
        base = [4.0] * 24
        config = TariffConfig(enabled=True, tiers=[
            TariffTier(name="peak", hours=[18, 19], multiplier=2.0),
            TariffTier(name="off-peak", hours=[0, 1, 2], multiplier=0.5),
        ])
        result, _label = _apply_tariff_tiers(base, config)
        assert result[18] == 8.0
        assert result[0] == 2.0
        assert result[10] == 4.0  # unchanged

    def test_optimizer_with_tariff(self):
        hours = _make_hours()
        battery = _make_battery()
        tariff_config = TariffConfig(enabled=True, tiers=[
            TariffTier(name="peak", hours=[18, 19, 20, 21], multiplier=3.0),
            TariffTier(name="off-peak", hours=[0, 1, 2, 3, 4, 5], multiplier=0.5),
        ])
        resp = optimize(hours=hours, battery=battery, directives=[],
                        scenario_id="TARIFF-TEST", tariff_config=tariff_config)
        assert resp.tariff_tier_label in ("peak", "off-peak")
        assert resp.total_cost_bdt > 0


# ---------------------------------------------------------------------------
# Degradation tests
# ---------------------------------------------------------------------------

class TestDegradation:
    def test_no_degradation(self):
        charge = [10.0] * 24
        discharge = [10.0] * 24
        cost, cycles = _compute_degradation_cost(charge, discharge, None)
        assert cost == 0.0
        assert cycles == 0.0

    def test_degradation_disabled(self):
        charge = [10.0] * 24
        discharge = [10.0] * 24
        deg = BatteryDegradation(enabled=False)
        cost, _cycles = _compute_degradation_cost(charge, discharge, deg)
        assert cost == 0.0

    def test_degradation_cost(self):
        charge = [50.0] * 24
        discharge = [50.0] * 24
        deg = BatteryDegradation(enabled=True, cost_per_cycle_bdt=1.0)
        cost, cycles = _compute_degradation_cost(charge, discharge, deg)
        assert cost > 0
        assert cycles > 0

    def test_optimizer_with_degradation(self):
        hours = _make_hours()
        battery = _make_battery()
        degradation = BatteryDegradation(enabled=True, cost_per_cycle_bdt=2.0, max_cycles=3000)
        resp = optimize(hours=hours, battery=battery, directives=[],
                        scenario_id="DEG-TEST", degradation=degradation)
        assert resp.degradation_cost_bdt >= 0
        assert resp.total_cycles >= 0
