# GridWise — Smart Campus Energy Optimisation Service

> **BUP CSE Fest 2026 Hackathon · Online Preliminary Round**

An LLM-assisted energy scheduling service that interprets natural-language operator notes, converts them into structured directives, validates them through deterministic guardrails, and produces a minimum-cost 24-hour energy schedule via Mixed-Integer Linear Programming (MILP).

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      POST /optimize-energy                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────┐  │
│  │  Operator    │───▶│   LLM Layer  │───▶│  Deterministic     │  │
│  │  Notes       │    │  (OpenAI-    │    │  Guardrails        │  │
│  │  (1-3 notes) │    │  compatible) │    │  (validation +     │  │
│  └─────────────┘    └──────────────┘    │   normalisation)   │  │
│                                         └────────┬───────────┘  │
│                                                  │               │
│                                                  ▼               │
│                                         ┌────────────────────┐  │
│                                         │  MILP Optimizer    │  │
│                                         │  (PuLP / CBC)      │  │
│                                         │  - 24-hour slots   │  │
│                                         │  - Battery SOC     │  │
│                                         │  - Energy balance  │  │
│                                         │  - Directive hard  │  │
│                                         │    constraints     │  │
│                                         └────────┬───────────┘  │
│                                                  │               │
│                                                  ▼               │
│                                         ┌────────────────────┐  │
│                                         │  Optimal 24-hour   │  │
│                                         │  Schedule Response │  │
│                                         └────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Pipeline Steps

1. **LLM Interpretation** — An OpenAI-compatible language model reads 1–3 natural-language operator notes and returns a structured `directive_interpretation` array. Each note maps to exactly one supported directive type or `no_op`.

2. **Deterministic Guardrails** — Validates the LLM output against strict rules: correct directive types, valid hours (unique integers 0–23, ascending), correct `applies` semantics, valid numeric ranges, and matching `structured_adjustment` shapes. Invalid output is corrected or rejected.

3. **MILP Optimizer** — Formulates the 24-hour scheduling problem as a Mixed-Integer Linear Program. Uses PuLP with the CBC solver to minimise total grid electricity cost (`SUM(grid_kwh × tariff)`) while respecting energy balance, battery state-of-charge bounds, charge/discharge rate limits, all operator-directive hard constraints, and end-of-day battery neutrality.

---

## Supported Directive Types

| Directive Type | Meaning | `structured_adjustment` Shape |
|---|---|---|
| `solar_reduction` | Reduce usable solar during specific hours | `{"hours": [...], "factor": float}` |
| `minimum_battery_reserve` | Keep battery energy above a level | `{"hours": [...], "minimum_energy_kwh": number}` |
| `no_charge_window` | Prohibit battery charging | `{"hours": [...]}` |
| `no_discharge_window` | Prohibit battery discharging | `{"hours": [...]}` |
| `max_grid_window` | Cap grid import per hour | `{"hours": [...], "max_grid_kwh": number}` |
| `no_op` | Note does not affect schedule | `null` |

---

## Quick Start

### Prerequisites

- Python 3.11+
- An OpenAI-compatible API key (OpenAI, Azure OpenAI, or any compatible provider)

### 1. Clone and configure

```bash
git clone <repository-url>
cd gridwise
cp .env.example .env
```

Edit `.env` and set your `LLM_API_KEY`:

```env
LLM_API_KEY=sk-your-key-here
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
```

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
pip install -r requirements.txt
```

### 3. Start the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Verify health

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

### 5. Test with a sample request

```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "SAMPLE-TEST",
    "operator_notes": [
      "The cafeteria menu changes tomorrow."
    ],
    "hours": [
      {"hour":0,"demand_kwh":90,"solar_kwh":0,"tariff_bdt_per_kwh":6},
      {"hour":1,"demand_kwh":85,"solar_kwh":0,"tariff_bdt_per_kwh":6},
      {"hour":2,"demand_kwh":80,"solar_kwh":0,"tariff_bdt_per_kwh":5},
      {"hour":3,"demand_kwh":80,"solar_kwh":0,"tariff_bdt_per_kwh":5},
      {"hour":4,"demand_kwh":85,"solar_kwh":0,"tariff_bdt_per_kwh":5},
      {"hour":5,"demand_kwh":95,"solar_kwh":0,"tariff_bdt_per_kwh":6},
      {"hour":6,"demand_kwh":110,"solar_kwh":5,"tariff_bdt_per_kwh":8},
      {"hour":7,"demand_kwh":130,"solar_kwh":20,"tariff_bdt_per_kwh":10},
      {"hour":8,"demand_kwh":150,"solar_kwh":50,"tariff_bdt_per_kwh":12},
      {"hour":9,"demand_kwh":165,"solar_kwh":90,"tariff_bdt_per_kwh":14},
      {"hour":10,"demand_kwh":175,"solar_kwh":130,"tariff_bdt_per_kwh":16},
      {"hour":11,"demand_kwh":180,"solar_kwh":160,"tariff_bdt_per_kwh":16},
      {"hour":12,"demand_kwh":185,"solar_kwh":180,"tariff_bdt_per_kwh":15},
      {"hour":13,"demand_kwh":180,"solar_kwh":170,"tariff_bdt_per_kwh":14},
      {"hour":14,"demand_kwh":170,"solar_kwh":140,"tariff_bdt_per_kwh":13},
      {"hour":15,"demand_kwh":165,"solar_kwh":90,"tariff_bdt_per_kwh":14},
      {"hour":16,"demand_kwh":170,"solar_kwh":45,"tariff_bdt_per_kwh":18},
      {"hour":17,"demand_kwh":185,"solar_kwh":10,"tariff_bdt_per_kwh":22},
      {"hour":18,"demand_kwh":205,"solar_kwh":0,"tariff_bdt_per_kwh":28},
      {"hour":19,"demand_kwh":215,"solar_kwh":0,"tariff_bdt_per_kwh":30},
      {"hour":20,"demand_kwh":205,"solar_kwh":0,"tariff_bdt_per_kwh":26},
      {"hour":21,"demand_kwh":175,"solar_kwh":0,"tariff_bdt_per_kwh":18},
      {"hour":22,"demand_kwh":135,"solar_kwh":0,"tariff_bdt_per_kwh":10},
      {"hour":23,"demand_kwh":105,"solar_kwh":0,"tariff_bdt_per_kwh":7}
    ],
    "battery": {
      "capacity_kwh": 220,
      "initial_energy_kwh": 110,
      "minimum_energy_kwh": 40,
      "max_charge_kwh_per_hour": 50,
      "max_discharge_kwh_per_hour": 50
    }
  }'
```

---

## Project Structure

```
gridwise/
├── app/
│   ├── __init__.py         # Package metadata
│   ├── config.py           # Environment-based configuration
│   ├── main.py             # FastAPI application + endpoints
│   ├── models.py           # Pydantic request/response models
│   ├── llm.py              # LLM integration (OpenAI-compatible API)
│   ├── guardrails.py       # Deterministic validation of LLM output
│   └── optimizer.py        # MILP optimizer (PuLP / CBC)
├── tests/
│   ├── __init__.py
│   ├── test_api.py         # API endpoint integration tests
│   ├── test_guardrails.py  # Guardrail validation tests
│   └── test_optimizer.py   # Optimizer correctness tests
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GRIDWISE_HOST` | `0.0.0.0` | Server bind address |
| `GRIDWISE_PORT` | `8000` | Server port |
| `LLM_API_KEY` | _(required)_ | API key for the LLM provider |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `LLM_MODEL` | `gpt-4o-mini` | Model identifier |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature |
| `LLM_MAX_TOKENS` | `2048` | Maximum response tokens |
| `LLM_TIMEOUT` | `30` | HTTP timeout in seconds |
| `OPTIMIZER_TIMEOUT` | `30` | Optimizer time limit in seconds |

---

## Docker

### Build and run

```bash
cp .env.example .env
# Edit .env with your LLM_API_KEY

docker compose up --build
```

### Pullable fallback image

```bash
docker build -t gridwise:latest .
docker run -p 8000:8000 --env-file .env gridwise:latest
```

The container exposes port 8000, binds to `0.0.0.0`, and includes a built-in health check.

---

## Running Tests

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio anyio

pytest tests/ -v
```

---

## API Contract

### `GET /health`

**Response:** `200 OK`

```json
{"status": "ok"}
```

### `POST /optimize-energy`

**Request body:**

```json
{
  "scenario_id": "string",
  "operator_notes": ["string", "..."],
  "hours": [
    {
      "hour": 0,
      "demand_kwh": 90.0,
      "solar_kwh": 0.0,
      "tariff_bdt_per_kwh": 6.0
    }
  ],
  "battery": {
    "capacity_kwh": 220.0,
    "initial_energy_kwh": 110.0,
    "minimum_energy_kwh": 40.0,
    "max_charge_kwh_per_hour": 50.0,
    "max_discharge_kwh_per_hour": 50.0
  }
}
```

**Response body:**

```json
{
  "scenario_id": "string",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [12, 13],
        "factor": 0.25
      },
      "explanation": "Solar reduced to 25% during panel cleaning."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 90.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 110.0
    }
  ],
  "total_grid_kwh": 2692.5,
  "total_cost_bdt": 38365.0,
  "peak_grid_kwh": 175.0,
  "plan_summary": "Schedule optimised to minimise total grid electricity cost."
}
```

---

## How the Optimizer Works

The optimizer formulates the 24-hour scheduling problem as a **Mixed-Integer Linear Program (MILP)**:

**Decision variables per hour (0–23):**
- `grid_kwh[h]` — grid electricity purchased
- `solar_used_kwh[h]` — solar energy consumed
- `charge[h]` — energy added to battery
- `discharge[h]` — energy removed from battery
- `battery_energy[h]` — state of charge after hour h
- `is_charging[h]` — binary: 1 if charging
- `is_discharging[h]` — binary: 1 if discharging

**Objective:** Minimise `SUM(grid_kwh[h] × tariff[h])` for h = 0..23

**Constraints:**
1. **Energy balance:** `grid + solar_used + discharge = demand + charge`
2. **Solar cap:** `solar_used[h] ≤ effective_solar[h]`
3. **Battery transition:** `E[h] = E[h-1] + charge - discharge`
4. **Battery bounds:** `min_reserve[h] ≤ E[h] ≤ capacity`
5. **Rate limits:** `charge ≤ max_charge_rate × is_charging`
6. **Mutual exclusion:** `is_charging + is_discharging ≤ 1`
7. **Directive constraints:** charge/discharge windows, reserve, grid caps
8. **End-of-day neutrality:** `E[23] = E_initial`

---

## Design Decisions

### Why MILP over heuristic approaches?

- **Optimal guarantee:** MILP finds the provably optimal solution (within the time limit).
- **Constraint expressiveness:** Binary variables naturally model mutual exclusion of charge/discharge actions.
- **Deterministic:** Same input always produces the same output — critical for judge reproducibility.

### Why guardrails before optimization?

The LLM produces untrusted structured data. Deterministic validation ensures:
- Correct directive types (no hallucinated types)
- Valid hours (unique integers 0–23, ascending)
- Correct `applies` semantics (only `no_op` can have `applies=false`)
- Valid numeric ranges (solar factor in [0,1], non-negative reserves)
- Matching `structured_adjustment` shapes per directive type

### Why OpenAI-compatible API format?

Flexibility. Teams can use OpenAI, Azure OpenAI, Anthropic (via proxy), local models (Ollama, vLLM), or any provider that implements the chat completions endpoint format.

---

## Known Limitations

- The LLM call adds latency (typically 1–5 seconds depending on the provider and model).
- The MILP solver has a 30-second time limit; highly complex scenarios with many simultaneous directives may not reach provable optimality within this window (but will still produce a valid solution).
- The service does not persist data — each request is stateless.

---

## License

This project was developed for the BUP CSE Fest 2026 Hackathon.
