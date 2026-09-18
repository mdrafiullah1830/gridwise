"""FastAPI application — GridWise Smart Campus Energy Optimisation Service."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .guardrails import GuardrailError, validate_directives
from .llm import interpret_notes, to_directive_interpretations
from .models import (
    BaselineResponse,
    BatteryDegradation,
    CarbonOptimizeRequest,
    CarbonOptimizeResponse,
    CompareRequest,
    CompareResponse,
    DirectiveInterpretation,
    DirectiveType,
    OptimizeRequest,
    OptimizeResponse,
    ScenarioSummary,
    TariffConfig,
    Violation,
    ViolationSeverity,
    WhatIfPoint,
    WhatIfRequest,
    WhatIfResponse,
)
from .optimizer import optimize, optimize_carbon

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("gridwise")

STATIC_DIR = Path(__file__).parent / "static"
PUBLIC_DIR = Path(__file__).parent.parent / "public"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY is not set — LLM calls will fail at runtime")
    logger.info("GridWise starting — model=%s, base_url=%s, vercel=%s",
                settings.llm_model, settings.llm_base_url,
                os.environ.get("VERCEL", "0") == "1")
    yield
    logger.info("GridWise shutting down")


app = FastAPI(
    title="GridWise",
    description="Smart Campus Energy Optimisation — LLM-Assisted Operator Directive Interpretation",
    version="4.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allow_origins,
    allow_credentials=_settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Also mount public/ for Vercel deployment
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    # Serve from public/ if available (Vercel), otherwise from app/static/
    public_index = PUBLIC_DIR / "index.html"
    if public_index.exists():
        return FileResponse(str(public_index))
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/scenarios")
async def scenarios() -> JSONResponse:
    samples_path = Path(get_settings().samples_file)
    if not samples_path.is_absolute():
        samples_path = Path(__file__).resolve().parent.parent / samples_path
    try:
        raw = samples_path.read_text()
        data = json.loads(raw)
        cases = data.get("cases", [])
        samples = []
        for case in cases:
            inp = case.get("input", {})
            samples.append({
                "id": inp.get("scenario_id", case.get("id", "UNKNOWN")),
                "notes": inp.get("operator_notes", []),
                "hours": inp.get("hours", []),
                "battery": inp.get("battery", {}),
            })
        return JSONResponse(content={"count": len(samples), "samples": samples})
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        logger.error("Failed to load samples: %s", exc)
        return JSONResponse(content={"count": 0, "samples": [], "error": str(exc)}, status_code=500)


@app.post("/optimize-energy")
async def optimize_energy(request: Request, body: OptimizeRequest) -> OptimizeResponse:
    t0 = time.monotonic()

    try:
        raw_directives = await interpret_notes(body.operator_notes)
    except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
        logger.error("LLM call failed: %s", exc)
        raw_directives = [
            {"note_index": i, "applies": False, "directive_type": "no_op",
             "structured_adjustment": None, "explanation": str(exc)}
            for i in range(len(body.operator_notes))
        ]

    directives = to_directive_interpretations(raw_directives)

    try:
        directives = validate_directives(directives, body.hours, len(body.operator_notes))
    except GuardrailError as exc:
        logger.error("Guardrail failure: %s", exc)
        raise HTTPException(status_code=422, detail=f"Guardrails: {exc}") from exc

    # Parse optional tariff config and degradation from request body
    raw_body = await request.json()
    tariff_config = None
    degradation = None
    if raw_body.get("tariff_config"):
        tariff_config = TariffConfig(**raw_body["tariff_config"])
    if raw_body.get("degradation"):
        degradation = BatteryDegradation(**raw_body["degradation"])

    try:
        response = optimize(
            hours=body.hours, battery=body.battery, directives=directives,
            scenario_id=body.scenario_id, tariff_config=tariff_config,
            degradation=degradation,
        )
    except RuntimeError as exc:
        logger.error("Optimizer failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Optimizer: {exc}") from exc

    # Detect constraint violations
    from .alerts import detect_violations, violations_summary
    violations = detect_violations(response.hourly_plan, body.hours, body.battery, list(directives))
    response.violations = violations
    response.violation_summary = violations_summary(violations)

    elapsed = time.monotonic() - t0
    logger.info("scenario=%s cost=%.2f elapsed=%.3fs violations=%d", body.scenario_id, response.total_cost_bdt, elapsed, len(violations))
    return response


@app.post("/optimize-energy/baseline", response_model=BaselineResponse)
async def optimize_energy_baseline(request: Request, body: OptimizeRequest) -> BaselineResponse:
    try:
        raw_directives = await interpret_notes(body.operator_notes)
    except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
        raw_directives = [
            {"note_index": i, "applies": False, "directive_type": "no_op",
             "structured_adjustment": None, "explanation": str(exc)}
            for i in range(len(body.operator_notes))
        ]

    directives = to_directive_interpretations(raw_directives)
    try:
        directives = validate_directives(directives, body.hours, len(body.operator_notes))
    except GuardrailError as exc:
        raise HTTPException(status_code=422, detail=f"Guardrails: {exc}") from exc

    try:
        optimised = optimize(hours=body.hours, battery=body.battery, directives=directives, scenario_id=body.scenario_id)
        baseline = optimize(
            hours=body.hours, battery=body.battery,
            directives=[DirectiveInterpretation(
                note_index=i, applies=False, directive_type=DirectiveType.NO_OP,
                structured_adjustment=None, explanation="baseline"
            ) for i in range(len(body.operator_notes))],
            scenario_id=f"{body.scenario_id}-BASELINE",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Optimizer: {exc}") from exc

    savings_bdt = baseline.total_cost_bdt - optimised.total_cost_bdt
    savings_pct = (savings_bdt / baseline.total_cost_bdt * 100.0) if baseline.total_cost_bdt > 0 else 0.0

    return BaselineResponse(
        scenario_id=body.scenario_id,
        baseline_cost_bdt=baseline.total_cost_bdt,
        optimised_cost_bdt=optimised.total_cost_bdt,
        savings_bdt=round(savings_bdt, 2),
        savings_pct=round(savings_pct, 2),
        baseline_grid_kwh=baseline.total_grid_kwh,
        optimised_grid_kwh=optimised.total_grid_kwh,
        baseline_peak_grid_kwh=baseline.peak_grid_kwh,
        optimised_peak_grid_kwh=optimised.peak_grid_kwh,
        baseline_plan=baseline.hourly_plan,
        optimised_plan=optimised.hourly_plan,
        solver_status=optimised.solver_status,
        solve_time_ms=optimised.solve_time_ms,
    )


@app.post("/compare")
async def compare_scenarios(request: Request, body: CompareRequest) -> CompareResponse:
    summaries = []
    for req in body.scenarios:
        try:
            raw_directives = await interpret_notes(req.operator_notes)
        except (RuntimeError, ConnectionError, TimeoutError, ValueError):
            raw_directives = [
                {"note_index": i, "applies": False, "directive_type": "no_op",
                 "structured_adjustment": None, "explanation": "LLM unavailable"}
                for i in range(len(req.operator_notes))
            ]
        directives = to_directive_interpretations(raw_directives)
        try:
            directives = validate_directives(directives, req.hours, len(req.operator_notes))
        except GuardrailError:
            pass

        try:
            baseline = optimize(
                hours=req.hours, battery=req.battery,
                directives=[DirectiveInterpretation(
                    note_index=i, applies=False, directive_type=DirectiveType.NO_OP,
                    structured_adjustment=None, explanation="baseline"
                ) for i in range(len(req.operator_notes))],
                scenario_id=f"{req.scenario_id}-BASE",
            )
            optimised = optimize(hours=req.hours, battery=req.battery, directives=directives, scenario_id=req.scenario_id)
            savings = baseline.total_cost_bdt - optimised.total_cost_bdt
            savings_pct = (savings / baseline.total_cost_bdt * 100) if baseline.total_cost_bdt > 0 else 0
        except RuntimeError:
            continue

        summaries.append(ScenarioSummary(
            scenario_id=req.scenario_id,
            total_cost_bdt=optimised.total_cost_bdt,
            total_grid_kwh=optimised.total_grid_kwh,
            peak_grid_kwh=optimised.peak_grid_kwh,
            savings_bdt=round(savings, 2),
            savings_pct=round(savings_pct, 2),
            hourly_plan=optimised.hourly_plan,
            directive_count=len([d for d in directives if d.applies and d.directive_type != DirectiveType.NO_OP]),
        ))

    if not summaries:
        raise HTTPException(status_code=422, detail="All scenarios failed")

    best = min(summaries, key=lambda s: s.total_cost_bdt)
    worst = max(summaries, key=lambda s: s.total_cost_bdt)

    return CompareResponse(
        scenarios=summaries,
        best_scenario_id=best.scenario_id,
        cost_difference_bdt=round(worst.total_cost_bdt - best.total_cost_bdt, 2),
    )


@app.post("/what-if")
async def what_if(request: Request, body: WhatIfRequest) -> WhatIfResponse:
    points = []

    try:
        raw_directives = await interpret_notes(body.operator_notes)
    except (RuntimeError, ConnectionError, TimeoutError, ValueError):
        raw_directives = [
            {"note_index": i, "applies": False, "directive_type": "no_op",
             "structured_adjustment": None, "explanation": "LLM unavailable"}
            for i in range(len(body.operator_notes))
        ]

    directives = to_directive_interpretations(raw_directives)
    try:
        directives = validate_directives(directives, body.hours, len(body.operator_notes))
    except GuardrailError:
        pass

    for val in body.values:
        battery = body.battery.model_copy()
        if body.param == "capacity_kwh":
            battery.capacity_kwh = val
        elif body.param == "minimum_energy_kwh":
            battery.minimum_energy_kwh = val
        elif body.param == "max_charge_kwh_per_hour":
            battery.max_charge_kwh_per_hour = val
        elif body.param == "max_discharge_kwh_per_hour":
            battery.max_discharge_kwh_per_hour = val
        elif body.param == "initial_energy_kwh":
            battery.initial_energy_kwh = val
        else:
            raise HTTPException(status_code=422, detail=f"Unknown param: {body.param}")

        try:
            resp = optimize(hours=body.hours, battery=battery, directives=directives, scenario_id=body.scenario_id)
            points.append(WhatIfPoint(
                value=val, total_cost_bdt=resp.total_cost_bdt,
                total_grid_kwh=resp.total_grid_kwh, peak_grid_kwh=resp.peak_grid_kwh,
            ))
        except RuntimeError:
            continue

    baseline_cost = points[0].total_cost_bdt if points else 0
    return WhatIfResponse(scenario_id=body.scenario_id, param=body.param, points=points, baseline_cost_bdt=baseline_cost)


@app.post("/optimize-carbon")
async def optimize_carbon_endpoint(request: Request, body: CarbonOptimizeRequest):
    try:
        raw_directives = await interpret_notes(body.operator_notes)
    except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
        raw_directives = [
            {"note_index": i, "applies": False, "directive_type": "no_op",
             "structured_adjustment": None, "explanation": str(exc)}
            for i in range(len(body.operator_notes))
        ]

    directives = to_directive_interpretations(raw_directives)
    try:
        directives = validate_directives(directives, body.hours, len(body.operator_notes))
    except GuardrailError as exc:
        raise HTTPException(status_code=422, detail=f"Guardrails: {exc}") from exc

    try:
        resp, carbon, weighted = optimize_carbon(
            hours=body.hours, battery=body.battery, directives=directives,
            scenario_id=body.scenario_id, carbon_factor=body.carbon_factor_kg_per_kwh,
            cost_weight=body.cost_weight, carbon_weight=body.carbon_weight,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Optimizer: {exc}") from exc

    return CarbonOptimizeResponse(
        scenario_id=resp.scenario_id, directive_interpretation=resp.directive_interpretation,
        hourly_plan=resp.hourly_plan, total_grid_kwh=resp.total_grid_kwh,
        total_cost_bdt=resp.total_cost_bdt, peak_grid_kwh=resp.peak_grid_kwh,
        plan_summary=resp.plan_summary, solver_status=resp.solver_status,
        solve_time_ms=resp.solve_time_ms, objective_value=resp.objective_value,
        total_carbon_kg=carbon, baseline_carbon_kg=0, carbon_savings_kg=0,
        weighted_objective=weighted,
    )


@app.get("/history/trend")
async def get_cost_trend(limit: int = 50, scenario_id: str | None = None):
    from .database import get_cost_trend as db_trend
    trend = db_trend(limit=limit, scenario_id=scenario_id)
    return JSONResponse(content={"trend": trend, "count": len(trend)})


@app.get("/history")
async def get_history(limit: int = 50, offset: int = 0):
    from .database import get_runs, get_stats
    runs = get_runs(limit=limit, offset=offset)
    stats = get_stats()
    return JSONResponse(content={"runs": runs, "stats": stats})


@app.get("/history/{run_id}")
async def get_history_run(run_id: int):
    from .database import get_run
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse(content=run)


@app.delete("/history/{run_id}")
async def delete_history_run(run_id: int):
    from .database import delete_run
    if not delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse(content={"deleted": True})


@app.post("/history/save")
async def save_history_run(request: Request):
    from .database import save_run
    body = await request.json()
    run_id = save_run(
        scenario_id=body.get("scenario_id", "UNKNOWN"),
        notes=body.get("notes", []),
        response=body.get("response", {}),
        baseline=body.get("baseline"),
        elapsed_ms=body.get("elapsed_ms"),
        total_carbon_kg=body.get("total_carbon_kg", 0.0),
    )
    return JSONResponse(content={"run_id": run_id})


@app.get("/templates")
async def get_templates():
    from .models import BatterySpec, HourEntry, ScenarioTemplate

    templates = [
        ScenarioTemplate(
            id="exam-day", name="Exam Day",
            description="High demand, minimal solar disruption — battery reserved for peak hours",
            notes=["Keep battery above 50% for emergency backup during exams"],
            battery=BatterySpec(capacity_kwh=220, initial_energy_kwh=110, minimum_energy_kwh=40,
                                max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50),
            hours=[HourEntry(hour=h, demand_kwh=180 if 8 <= h <= 17 else 90,
                             solar_kwh=0 if h < 6 or h > 18 else (h - 5) * 30,
                             tariff_bdt_per_kwh=10 if 8 <= h <= 17 else 5) for h in range(24)],
        ),
        ScenarioTemplate(
            id="rainy-day", name="Rainy Day",
            description="Low solar, high demand — maximise grid import during cheap hours",
            notes=["Solar panels produce almost no power today — rely on grid and battery"],
            battery=BatterySpec(capacity_kwh=220, initial_energy_kwh=180, minimum_energy_kwh=40,
                                max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50),
            hours=[HourEntry(hour=h, demand_kwh=150 if 6 <= h <= 22 else 80,
                             solar_kwh=max(0, 5 - abs(h - 12)) if 6 <= h <= 18 else 0,
                             tariff_bdt_per_kwh=8 if 18 <= h <= 22 else 4) for h in range(24)],
        ),
        ScenarioTemplate(
            id="festival-night", name="Festival Night",
            description="Extended evening demand — schedule battery discharge for peak night hours",
            notes=["Schedule battery to power the load from 19:00 to 02:00", "Avoid grid import above 60 kWh per hour during peak"],
            battery=BatterySpec(capacity_kwh=220, initial_energy_kwh=200, minimum_energy_kwh=40,
                                max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50),
            hours=[HourEntry(hour=h, demand_kwh=250 if 18 <= h <= 23 or h <= 2 else 100,
                             solar_kwh=0 if h < 6 or h > 18 else (h - 5) * 25,
                             tariff_bdt_per_kwh=15 if 18 <= h <= 23 else 5) for h in range(24)],
        ),
        ScenarioTemplate(
            id="solar-cleaning", name="Solar Panel Cleaning",
            description="Noon cleaning — apply solar reduction factor for washing window",
            notes=["Facilities will wash the rooftop solar panels from noon until 2 PM. Usable solar drops to 25%"],
            battery=BatterySpec(capacity_kwh=220, initial_energy_kwh=110, minimum_energy_kwh=40,
                                max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50),
            hours=[HourEntry(hour=h, demand_kwh=160 if 8 <= h <= 18 else 85,
                             solar_kwh=0 if h < 6 or h > 19 else (h - 5) * 28,
                             tariff_bdt_per_kwh=12 if 8 <= h <= 18 else 5) for h in range(24)],
        ),
        ScenarioTemplate(
            id="holiday-mode", name="Holiday Mode",
            description="Minimal demand — charge battery fully, minimal grid usage",
            notes=["Charge battery to full by noon", "Keep grid import minimal throughout the day"],
            battery=BatterySpec(capacity_kwh=220, initial_energy_kwh=50, minimum_energy_kwh=20,
                                max_charge_kwh_per_hour=50, max_discharge_kwh_per_hour=50),
            hours=[HourEntry(hour=h, demand_kwh=50 if 8 <= h <= 18 else 30,
                             solar_kwh=0 if h < 7 or h > 18 else (h - 6) * 20,
                             tariff_bdt_per_kwh=3) for h in range(24)],
        ),
    ]

    return JSONResponse(content={"count": len(templates), "templates": [t.model_dump() for t in templates]})


# ---------------------------------------------------------------------------
# PDF Report
# ---------------------------------------------------------------------------

@app.post("/report")
async def generate_pdf_report(request: Request):
    """Generate a comprehensive PDF report from optimisation results."""
    from fastapi.responses import Response

    from .pdf_report import generate_report

    body = await request.json()
    response = body.get("response", {})
    baseline = body.get("baseline")
    whatif = body.get("whatif")
    compare = body.get("compare")
    carbon = body.get("carbon")
    demo_results = body.get("demo_results")

    try:
        pdf_bytes = generate_report(
            response=response, baseline=baseline, whatif=whatif,
            compare=compare, carbon=carbon, demo_results=demo_results,
        )
        scenario_id = response.get("scenario_id", "report")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="gridwise-{scenario_id}.pdf"'},
        )
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Carbon Stats (v4.0)
# ---------------------------------------------------------------------------

@app.get("/carbon/stats")
async def get_carbon_stats():
    from .database import get_carbon_stats as db_carbon_stats
    stats = db_carbon_stats()
    return JSONResponse(content=stats)


# ---------------------------------------------------------------------------
# WebSocket — Live Optimisation Streaming (v4.0)
# ---------------------------------------------------------------------------

@app.websocket("/ws/optimize")
async def ws_optimize(websocket: WebSocket):
    """Stream optimisation progress via WebSocket."""
    await websocket.accept()
    try:
        body = await websocket.receive_json()
        notes = body.get("operator_notes", [])
        hours_raw = body.get("hours", [])
        battery_raw = body.get("battery", {})

        await websocket.send_json({"step": "connecting", "message": "Connected to GridWise", "progress": 10})

        # Parse models
        from .models import BatterySpec, HourEntry
        hours = [HourEntry(**h) for h in hours_raw]
        battery = BatterySpec(**battery_raw)

        await websocket.send_json({"step": "interpreting", "message": "Interpreting operator notes with LLM...", "progress": 25})

        # LLM interpretation
        try:
            raw_directives = await interpret_notes(notes)
        except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
            raw_directives = [
                {"note_index": i, "applies": False, "directive_type": "no_op",
                 "structured_adjustment": None, "explanation": str(exc)}
                for i in range(len(notes))
            ]

        directives = to_directive_interpretations(raw_directives)
        await websocket.send_json({"step": "validating", "message": "Running guardrails validation...", "progress": 50})

        try:
            directives = validate_directives(directives, hours, len(notes))
        except GuardrailError as exc:
            await websocket.send_json({"step": "error", "message": f"Guardrail error: {exc}", "progress": 0})
            return

        await websocket.send_json({"step": "solving", "message": "Solving MILP optimisation...", "progress": 70})

        # Parse optional tariff/degradation
        tariff_config = None
        degradation = None
        if body.get("tariff_config"):
            tariff_config = TariffConfig(**body["tariff_config"])
        if body.get("degradation"):
            degradation = BatteryDegradation(**body["degradation"])

        try:
            response = optimize(
                hours=hours, battery=battery, directives=directives,
                scenario_id=body.get("scenario_id", "WS-OPTIMIZE"),
                tariff_config=tariff_config, degradation=degradation,
            )
        except RuntimeError as exc:
            await websocket.send_json({"step": "error", "message": f"Optimizer failed: {exc}", "progress": 0})
            return

        # Detect violations
        from .alerts import detect_violations, violations_summary
        violations = detect_violations(response.hourly_plan, hours, battery, list(directives))
        response.violations = violations
        response.violation_summary = violations_summary(violations)

        await websocket.send_json({"step": "complete", "message": "Optimisation complete!", "progress": 100, "response": response.model_dump()})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except (RuntimeError, ValueError, KeyError) as exc:
        logger.error("WebSocket error: %s", exc)
        try:
            await websocket.send_json({"step": "error", "message": str(exc), "progress": 0})
        except WebSocketDisconnect:
            pass
