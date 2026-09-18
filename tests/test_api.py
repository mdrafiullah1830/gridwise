"""Integration tests for the FastAPI application."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _sample_request() -> dict:
    """Minimal valid request (no operator notes for simplicity)."""
    demand = [
        90, 85, 80, 80, 85, 95, 110, 130, 150, 165,
        175, 180, 185, 180, 170, 165, 170, 185, 205, 215,
        205, 175, 135, 105,
    ]
    solar = [
        0, 0, 0, 0, 0, 0, 5, 20, 50, 90,
        130, 160, 180, 170, 140, 90, 45, 10, 0, 0,
        0, 0, 0, 0,
    ]
    tariff = [
        6, 6, 5, 5, 5, 6, 8, 10, 12, 14,
        16, 16, 15, 14, 13, 14, 18, 22, 28, 30,
        26, 18, 10, 7,
    ]
    return {
        "scenario_id": "TEST-API",
        "operator_notes": ["The cafeteria menu changes tomorrow."],
        "hours": [
            {"hour": h, "demand_kwh": demand[h], "solar_kwh": solar[h], "tariff_bdt_per_kwh": tariff[h]}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 220,
            "initial_energy_kwh": 110,
            "minimum_energy_kwh": 40,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50,
        },
    }


@pytest.mark.anyio
async def test_health_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_optimize_endpoint_mocked_llm() -> None:
    """Test /optimize-energy with a mocked LLM returning a no_op."""
    mock_llm = AsyncMock(
        return_value=[
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "distractor",
            }
        ]
    )

    with patch("app.main.interpret_notes", mock_llm):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/optimize-energy",
                json=_sample_request(),
                headers={"Content-Type": "application/json"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario_id"] == "TEST-API"
    assert len(body["directive_interpretation"]) == 1
    assert body["directive_interpretation"][0]["directive_type"] == "no_op"
    assert len(body["hourly_plan"]) == 24
    assert body["total_grid_kwh"] > 0
    assert body["total_cost_bdt"] > 0
    mock_llm.assert_called_once()


@pytest.mark.anyio
async def test_optimize_malformed_json() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/optimize-energy",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_optimize_missing_fields() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/optimize-energy",
            json={"scenario_id": "X"},
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code in (400, 422)
