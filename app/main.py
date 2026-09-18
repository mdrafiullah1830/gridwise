"""FastAPI application — GridWise Smart Campus Energy Optimisation Service.

Endpoints
---------
GET  /                  — Dashboard UI
GET  /health            — readiness probe
GET  /scenarios         — list available sample scenarios
POST /optimize-energy   — interpret operator notes + optimise 24-hour schedule
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .guardrails import GuardrailError, validate_directives
from .llm import interpret_notes, to_directive_interpretations
from .models import OptimizeRequest, OptimizeResponse
from .optimizer import optimize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_FILE = Path("/Users/mdrafiullah/Downloads/BUP_CSE_FEST_2026_Participant_Docs/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY is not set — LLM calls will fail at runtime")
    logger.info("GridWise starting — model=%s, base_url=%s", settings.llm_model, settings.llm_base_url)
    yield
    logger.info("GridWise shutting down")


app = FastAPI(
    title="GridWise",
    description="Smart Campus Energy Optimisation — LLM-Assisted Operator Directive Interpretation",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/scenarios")
async def scenarios() -> JSONResponse:
    """Return the 10 public sample cases for the dashboard."""
    try:
        raw = SAMPLES_FILE.read_text()
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
async def optimize_energy(request: OptimizeRequest) -> OptimizeResponse:
    """Interpret operator notes and produce an optimal 24-hour energy schedule."""
    t0 = time.monotonic()

    try:
        raw_directives = await interpret_notes(request.operator_notes)
    except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
        logger.error("LLM call failed: %s", exc)
        raw_directives = [
            {
                "note_index": i,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": f"LLM unavailable — note treated as no_op: {exc}",
            }
            for i in range(len(request.operator_notes))
        ]

    directives = to_directive_interpretations(raw_directives)

    try:
        directives = validate_directives(
            directives, request.hours, len(request.operator_notes)
        )
    except GuardrailError as exc:
        logger.error("Guardrail failure: %s", exc)
        raise HTTPException(
            status_code=422,
            detail=f"Directive interpretation failed guardrails: {exc}",
        ) from exc

    try:
        response = optimize(
            hours=request.hours,
            battery=request.battery,
            directives=directives,
            scenario_id=request.scenario_id,
        )
    except RuntimeError as exc:
        logger.error("Optimizer failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer failed: {exc}",
        ) from exc

    elapsed = time.monotonic() - t0
    logger.info(
        "scenario=%s directives=%d cost=%.2f elapsed=%.3fs",
        request.scenario_id,
        len(directives),
        response.total_cost_bdt,
        elapsed,
    )

    return response
