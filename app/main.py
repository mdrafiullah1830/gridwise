"""FastAPI application — GridWise Smart Campus Energy Optimisation Service.

Endpoints
---------
GET  /health          — readiness probe
POST /optimize-energy — interpret operator notes + optimise 24-hour schedule
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    settings = get_settings()
    if not settings.llm_api_key:
        logger.warning(
            "LLM_API_KEY is not set — LLM calls will fail at runtime"
        )
    logger.info(
        "GridWise starting — model=%s, base_url=%s",
        settings.llm_model,
        settings.llm_base_url,
    )
    yield
    logger.info("GridWise shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GridWise",
    description="Smart Campus Energy Optimisation — LLM-Assisted Operator Directive Interpretation",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    """Readiness probe — must return {"status": "ok"}."""
    return JSONResponse(content={"status": "ok"})


# ---------------------------------------------------------------------------
# Optimise endpoint
# ---------------------------------------------------------------------------

@app.post("/optimize-energy")
async def optimize_energy(request: OptimizeRequest) -> OptimizeResponse:
    """Interpret operator notes and produce an optimal 24-hour energy schedule.

    Pipeline:
    1. LLM interprets natural-language operator notes → structured directives
    2. Deterministic guardrails validate / correct LLM output
    3. MILP optimizer produces the minimum-cost 24-hour schedule
    """
    t0 = time.monotonic()

    # Step 1 — LLM interpretation
    try:
        raw_directives = await interpret_notes(request.operator_notes)
    except Exception as exc:  # noqa: BLE001 — intentional graceful degradation
        logger.error("LLM call failed: %s", exc)
        # Graceful degradation: treat all notes as no_op
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

    # Convert to typed models
    directives = to_directive_interpretations(raw_directives)

    # Step 2 — Guardrails
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

    # Step 3 — Optimise
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
