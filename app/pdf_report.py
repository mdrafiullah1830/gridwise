"""PDF report generator for GridWise optimisation results."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_COLORS = {
    "primary": colors.HexColor("#60a5fa"),
    "secondary": colors.HexColor("#a78bfa"),
    "success": colors.HexColor("#34d399"),
    "warning": colors.HexColor("#fb923c"),
    "danger": colors.HexColor("#f87171"),
    "dark": colors.HexColor("#0f172a"),
    "light": colors.HexColor("#f1f5f9"),
    "muted": colors.HexColor("#64748b"),
}


def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=ss["Title"], fontSize=28, leading=34,
                                textColor=_COLORS["dark"], spaceAfter=6, alignment=1),
        "subtitle": ParagraphStyle("subtitle", parent=ss["Normal"], fontSize=14, leading=18,
                                   textColor=_COLORS["muted"], alignment=1, spaceAfter=30),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=20, leading=26,
                             textColor=_COLORS["primary"], spaceBefore=20, spaceAfter=12),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=15, leading=20,
                             textColor=_COLORS["dark"], spaceBefore=14, spaceAfter=8),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=14,
                               textColor=_COLORS["dark"], spaceAfter=6),
        "body_bold": ParagraphStyle("body_bold", parent=ss["Normal"], fontSize=10, leading=14,
                                    textColor=_COLORS["dark"], spaceAfter=6, fontName="Helvetica-Bold"),
        "metric": ParagraphStyle("metric", parent=ss["Normal"], fontSize=24, leading=30,
                                 textColor=_COLORS["primary"], alignment=1, fontName="Helvetica-Bold"),
        "metric_label": ParagraphStyle("metric_label", parent=ss["Normal"], fontSize=9, leading=12,
                                       textColor=_COLORS["muted"], alignment=1, spaceAfter=10),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontSize=8, leading=10,
                                textColor=_COLORS["muted"]),
        "bullet": ParagraphStyle("bullet", parent=ss["Normal"], fontSize=10, leading=14,
                                 textColor=_COLORS["dark"], leftIndent=20, bulletIndent=10,
                                 spaceAfter=4),
    }


# ---------------------------------------------------------------------------
# Table helper
# ---------------------------------------------------------------------------

def _make_table(headers: list[str], rows: list[list], col_widths: list[float] | None = None) -> Table:
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _COLORS["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, _COLORS["muted"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _COLORS["light"]]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style))
    return t


# ---------------------------------------------------------------------------
# PDF Builder
# ---------------------------------------------------------------------------

def generate_report(
    response: dict,
    baseline: dict | None = None,
    whatif: dict | None = None,
    compare: dict | None = None,
    carbon: dict | None = None,
    demo_results: list[dict] | None = None,
) -> bytes:
    """Generate a comprehensive PDF report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    styles = _styles()
    story: list = []

    # ── COVER PAGE ──────────────────────────────────────
    story.append(Spacer(1, 60))
    story.append(Paragraph("GridWise", styles["title"]))
    story.append(Paragraph("Smart Campus Energy Optimisation Report", styles["subtitle"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Generated: {datetime.now(tz=timezone.utc).strftime('%d %B %Y, %H:%M UTC')}", styles["small"]))
    story.append(Paragraph(f"Scenario: {response.get('scenario_id', 'N/A')}", styles["small"]))
    story.append(Spacer(1, 40))

    # Executive Summary
    story.append(Paragraph("Executive Summary", styles["h1"]))
    story.append(Paragraph(
        "GridWise is an LLM-assisted energy optimisation service that interprets natural-language "
        "operator notes and produces cost-minimised 24-hour energy schedules using Mixed-Integer "
        "Linear Programming (MILP). This report presents the optimisation results, cost savings "
        "analysis, and sensitivity study for the campus energy system.",
        styles["body"],
    ))

    # Key Metrics
    story.append(Spacer(1, 10))
    metrics_data = [
        [Paragraph(f"BDT {response.get('total_cost_bdt', 0):,.2f}", styles["metric"]),
         Paragraph(f"{response.get('total_grid_kwh', 0):,.1f} kWh", styles["metric"]),
         Paragraph(f"{response.get('peak_grid_kwh', 0):,.1f} kWh", styles["metric"]),
         Paragraph(f"{response.get('solver_status', 'Optimal')}", styles["metric"])],
        [Paragraph("Total Cost (BDT)", styles["metric_label"]),
         Paragraph("Grid Total", styles["metric_label"]),
         Paragraph("Peak Grid", styles["metric_label"]),
         Paragraph("Solver Status", styles["metric_label"])],
    ]
    metrics_table = Table(metrics_data, colWidths=[doc.width / 4] * 4)
    metrics_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), _COLORS["light"]),
        ("BOX", (0, 0), (-1, -1), 1, _COLORS["primary"]),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _COLORS["muted"]),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(metrics_table)
    story.append(PageBreak())

    # ── SECTION 1: DIRECTIVE INTERPRETATION ─────────────
    story.append(Paragraph("1. LLM Directive Interpretation", styles["h1"]))
    story.append(Paragraph(
        "The system processed operator notes through an LLM and validated them via deterministic guardrails:",
        styles["body"],
    ))

    directives = response.get("directive_interpretation", [])
    if directives:
        dir_headers = ["#", "Type", "Applies", "Details", "Explanation"]
        dir_rows = []
        for d in directives:
            adj = d.get("structured_adjustment") or {}
            detail = ""
            if d.get("directive_type") == "solar_reduction":
                detail = f"Factor: {adj.get('factor', 'N/A')}, Hours: {adj.get('hours', [])}"
            elif d.get("directive_type") == "minimum_battery_reserve":
                detail = f"Reserve: {adj.get('minimum_energy_kwh', 'N/A')} kWh"
            elif "window" in d.get("directive_type", ""):
                detail = f"Hours: {adj.get('hours', [])}"
            elif d.get("directive_type") == "max_grid_window":
                detail = f"Max: {adj.get('max_grid_kwh', 'N/A')} kWh"

            dir_rows.append([
                str(d.get("note_index", "")),
                d.get("directive_type", "").replace("_", " ").title(),
                "Yes" if d.get("applies") else "No",
                detail[:40],
                (d.get("explanation", "") or "")[:50],
            ])
        story.append(_make_table(dir_headers, dir_rows, col_widths=[25, 80, 40, 120, 200]))
    story.append(PageBreak())

    # ── SECTION 2: 24-HOUR SCHEDULE ─────────────────────
    story.append(Paragraph("2. Optimised 24-Hour Schedule", styles["h1"]))
    schedule = response.get("hourly_plan", [])
    if schedule:
        sched_headers = ["Hr", "Grid", "Solar", "Action", "Batt kWh", "SOC kWh"]
        sched_rows = []
        for h in schedule:
            sched_rows.append([
                f"{h.get('hour', 0):02d}:00",
                f"{h.get('grid_kwh', 0):.1f}",
                f"{h.get('solar_used_kwh', 0):.1f}",
                h.get("battery_action", "idle").upper(),
                f"{h.get('battery_kwh', 0):.1f}",
                f"{h.get('battery_energy_after_kwh', 0):.1f}",
            ])
        story.append(_make_table(sched_headers, sched_rows, col_widths=[40, 55, 55, 55, 60, 60]))
    story.append(PageBreak())

    # ── SECTION 3: BASELINE COMPARISON ──────────────────
    if baseline:
        story.append(Paragraph("3. Baseline vs Optimised Comparison", styles["h1"]))
        story.append(Paragraph(
            f"Running the same scenario without directives gives a baseline cost of "
            f"BDT {baseline.get('baseline_cost_bdt', 0):,.2f}. The optimised schedule with "
            f"directives costs BDT {baseline.get('optimised_cost_bdt', 0):,.2f}, saving "
            f"BDT {baseline.get('savings_bdt', 0):,.2f} ({baseline.get('savings_pct', 0):.1f}%).",
            styles["body"],
        ))

        base_headers = ["Metric", "Baseline", "Optimised", "Savings"]
        base_rows = [
            ["Cost (BDT)", f"{baseline.get('baseline_cost_bdt', 0):,.2f}",
             f"{baseline.get('optimised_cost_bdt', 0):,.2f}",
             f"{baseline.get('savings_bdt', 0):,.2f} ({baseline.get('savings_pct', 0):.1f}%)"],
            ["Grid (kWh)", f"{baseline.get('baseline_grid_kwh', 0):,.1f}",
             f"{baseline.get('optimised_grid_kwh', 0):,.1f}",
             f"{baseline.get('baseline_grid_kwh', 0) - baseline.get('optimised_grid_kwh', 0):,.1f}"],
            ["Peak Grid (kWh)", f"{baseline.get('baseline_peak_grid_kwh', 0):,.1f}",
             f"{baseline.get('optimised_peak_grid_kwh', 0):,.1f}",
             f"{baseline.get('baseline_peak_grid_kwh', 0) - baseline.get('optimised_peak_grid_kwh', 0):,.1f}"],
        ]
        story.append(_make_table(base_headers, base_rows, col_widths=[80, 100, 100, 130]))
        story.append(PageBreak())

    # ── SECTION 4: CARBON ANALYSIS ──────────────────────
    if carbon:
        story.append(Paragraph("4. Carbon Footprint Analysis", styles["h1"]))
        story.append(Paragraph(
            "Multi-objective optimisation balancing cost and carbon emissions:",
            styles["body"],
        ))
        carbon_data = [
            ["Total Carbon", f"{carbon.get('total_carbon_kg', 0):.2f} kg CO₂"],
            ["Total Cost", f"BDT {carbon.get('total_cost_bdt', 0):,.2f}"],
            ["Grid Usage", f"{carbon.get('total_grid_kwh', 0):,.1f} kWh"],
            ["Weighted Objective", f"{carbon.get('weighted_objective', 0):.2f}"],
        ]
        story.append(_make_table(["Metric", "Value"], carbon_data, col_widths=[150, 200]))
        story.append(Spacer(1, 10))

    # ── SECTION 5: WHAT-IF ANALYSIS ─────────────────────
    if whatif and whatif.get("points"):
        story.append(Paragraph("5. What-If Sensitivity Analysis", styles["h1"]))
        param_name = whatif.get("param", "").replace("_", " ").title()
        story.append(Paragraph(
            f"Parameter: {param_name} — swept across {len(whatif['points'])} values",
            styles["body"],
        ))
        wi_headers = ["Value", "Cost (BDT)", "Grid (kWh)", "Peak (kWh)"]
        wi_rows = []
        for p in whatif["points"]:
            wi_rows.append([
                str(p.get("value", "")),
                f"{p.get('total_cost_bdt', 0):,.2f}",
                f"{p.get('total_grid_kwh', 0):,.1f}",
                f"{p.get('peak_grid_kwh', 0):,.1f}",
            ])
        story.append(_make_table(wi_headers, wi_rows, col_widths=[80, 100, 100, 100]))
        story.append(PageBreak())

    # ── SECTION 6: SCENARIO COMPARISON ──────────────────
    if compare and compare.get("scenarios"):
        story.append(Paragraph("6. Scenario Comparison", styles["h1"]))
        story.append(Paragraph(
            f"Best scenario: {compare.get('best_scenario_id', 'N/A')} — "
            f"saves BDT {compare.get('cost_difference_bdt', 0):,.2f} vs worst",
            styles["body"],
        ))
        comp_headers = ["Scenario", "Cost (BDT)", "Grid (kWh)", "Peak", "Savings %", "Directives"]
        comp_rows = []
        for s in compare["scenarios"]:
            comp_rows.append([
                s.get("scenario_id", ""),
                f"{s.get('total_cost_bdt', 0):,.2f}",
                f"{s.get('total_grid_kwh', 0):,.1f}",
                f"{s.get('peak_grid_kwh', 0):,.1f}",
                f"{s.get('savings_pct', 0):.1f}%",
                str(s.get("directive_count", 0)),
            ])
        story.append(_make_table(comp_headers, comp_rows, col_widths=[70, 75, 65, 50, 60, 60]))
        story.append(PageBreak())

    # ── SECTION 7: DEMO RESULTS ─────────────────────────
    if demo_results:
        story.append(Paragraph("7. Demo Results — All Sample Cases", styles["h1"]))
        demo_headers = ["Scenario", "Cost (BDT)", "Grid (kWh)", "Peak", "Status"]
        demo_rows = []
        for d in demo_results:
            demo_rows.append([
                d.get("scenario_id", ""),
                f"{d.get('total_cost_bdt', 0):,.2f}",
                f"{d.get('total_grid_kwh', 0):,.1f}",
                f"{d.get('peak_grid_kwh', 0):,.1f}",
                d.get("solver_status", "Optimal"),
            ])
        story.append(_make_table(demo_headers, demo_rows, col_widths=[80, 80, 70, 60, 70]))
        story.append(PageBreak())

    # ── SECTION 8: TECHNICAL METHODOLOGY ────────────────
    story.append(Paragraph("8. Technical Methodology", styles["h1"]))

    story.append(Paragraph("8.1 System Architecture", styles["h2"]))
    story.append(Paragraph(
        "GridWise follows a three-stage pipeline: LLM interpretation → Guardrails validation → "
        "MILP optimisation. The LLM converts natural-language operator notes into structured "
        "directive objects. Deterministic guardrails validate and correct these directives before "
        "feeding them to the PuLP/CBC MILP solver.",
        styles["body"],
    ))

    story.append(Paragraph("8.2 MILP Formulation", styles["h2"]))
    milp_items = [
        "<b>Objective:</b> Minimise total grid electricity cost = Σ(grid_h × tariff_h)",
        "<b>Decision Variables:</b> grid_h, solar_used_h, charge_h, discharge_h, energy_h (continuous), is_ch_h, is_dch_h (binary)",
        ("<b>Constraints:</b> Energy balance, solar cap, battery SOC transitions, rate limits, "
         "mutual exclusion (no simultaneous charge/discharge), directive constraints, "
         "end-of-day neutrality (energy_23 = initial_energy)"),
        "<b>Solver:</b> PuLP with CBC (Coin-or branch and cut), 30s time limit",
    ]
    for item in milp_items:
        story.append(Paragraph(f"• {item}", styles["bullet"]))

    story.append(Paragraph("8.3 Directive Types", styles["h2"]))
    directive_types = [
        ["solar_reduction", "Reduces solar by factor (0-1) during specified hours"],
        ["minimum_battery_reserve", "Enforces minimum battery energy (kWh) during hours"],
        ["no_charge_window", "Prohibits battery charging during specified hours"],
        ["no_discharge_window", "Prohibits battery discharging during specified hours"],
        ["max_grid_window", "Caps grid import (kWh) per hour during windows"],
        ["no_op", "Note does not affect energy schedule"],
    ]
    story.append(_make_table(["Directive", "Description"], directive_types, col_widths=[120, 300]))
    story.append(PageBreak())

    # ── SECTION 9: RECOMMENDATIONS ──────────────────────
    story.append(Paragraph("9. Recommendations & Future Work", styles["h2"]))
    recs = [
        "<b>Real-time Tariff Integration:</b> Connect to live grid pricing APIs for dynamic optimisation.",
        "<b>Weather API:</b> Use real weather forecasts for accurate solar predictions.",
        "<b>Multi-day Scheduling:</b> Extend to 48/72-hour or weekly planning horizons.",
        "<b>Battery Degradation:</b> Model cycle count and capacity fade for long-term cost optimisation.",
        "<b>Demand Response:</b> Participate in grid-level demand response programs for revenue.",
        "<b>Carbon Trading:</b> Integrate with carbon credit markets for additional value.",
        "<b>Federated Learning:</b> Enable multiple campuses to share optimisation insights.",
    ]
    for r in recs:
        story.append(Paragraph(f"• {r}", styles["bullet"]))

    story.append(PageBreak())

    # ── SECTION 10: API REFERENCE ───────────────────────
    story.append(Paragraph("10. API Reference", styles["h2"]))
    api_endpoints = [
        ["GET", "/health", "Health check", "200 OK"],
        ["GET", "/scenarios", "List 10 sample cases", "200 OK"],
        ["GET", "/templates", "List 5 scenario templates", "200 OK"],
        ["POST", "/optimize-energy", "LLM + MILP optimisation", "200 OK"],
        ["POST", "/optimize-energy/baseline", "Baseline vs optimised", "200 OK"],
        ["POST", "/compare", "Multi-scenario comparison", "200 OK"],
        ["POST", "/what-if", "Parameter sweep analysis", "200 OK"],
        ["POST", "/optimize-carbon", "Carbon-aware optimisation", "200 OK"],
        ["GET", "/history", "Run history", "200 OK"],
        ["GET", "/docs", "Swagger API docs", "200 OK"],
    ]
    story.append(_make_table(["Method", "Endpoint", "Description", "Response"], api_endpoints,
                             col_widths=[40, 130, 160, 70]))

    # ── FOOTER ──────────────────────────────────────────
    story.append(Spacer(1, 30))
    story.append(Paragraph("—" * 60, styles["small"]))
    story.append(Paragraph(
        "GridWise v3.0 — BUP CSE Fest 2026 Hackathon · Smart Campus Energy Optimisation",
        styles["small"],
    ))

    # Build PDF
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
