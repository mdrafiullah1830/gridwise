"""LLM integration for operator-note interpretation.

Uses an OpenAI-compatible chat completions endpoint.  The model receives a
carefully engineered system prompt that instructs it to return **only** valid
JSON conforming to the ``directive_interpretation`` schema.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .config import get_settings
from .models import (
    DirectiveInterpretation,
    DirectiveType,
    StructuredAdjustment,
)

logger = logging.getLogger(__name__)

# Match a balanced JSON array (best-effort, used only as a fallback when
# ``json.loads`` fails on a slightly malformed LLM payload).
_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are GridWise, an expert energy-scheduling AI.  Your task is to interpret \
short natural-language operator notes for a smart-campus energy system and \
return a structured directive interpretation.

You MUST return a JSON array of directive objects — one per operator note, in \
the same order as the input notes.  Each object must contain exactly these \
fields:

- "note_index": integer, zero-based index of the note.
- "applies": boolean — true if the note affects today's 24-hour energy \
  schedule, false otherwise.
- "directive_type": one of "solar_reduction", "minimum_battery_reserve", \
  "no_charge_window", "no_discharge_window", "max_grid_window", "no_op".
- "structured_adjustment": an object whose shape depends on directive_type, \
  or null for no_op.
- "explanation": a one-sentence English explanation.

Directive-specific structured_adjustment shapes:

1. solar_reduction → {"hours": [int, …], "factor": float}
   - "hours" are the affected whole hours (0–23).
   - "factor" is the USABLE fraction remaining (e.g., 80% reduction → 0.2).

2. minimum_battery_reserve → {"hours": [int, …], "minimum_energy_kwh": number}
   - "hours" are the affected whole hours.
   - "minimum_energy_kwh" is the minimum energy (kWh) that must remain.

3. no_charge_window → {"hours": [int, …]}
   - Battery charging is prohibited during these hours.

4. no_discharge_window → {"hours": [int, …]}
   - Battery discharging is prohibited during these hours.

5. max_grid_window → {"hours": [int, …], "max_grid_kwh": number}
   - Grid import must not exceed the given kWh in each listed hour.

6. no_op → null
   - The note does not affect the current schedule.

Rules:
- Time windows use whole-hour intervals.  The start hour is INCLUDED and the \
  end hour is EXCLUDED: "1 PM to 3 PM" → [13, 14].
- "hours" arrays must be unique integers in ascending order.
- You must NOT invent demand, solar, tariff, or battery values.
- If the note is clearly unrelated to energy scheduling (e.g., library \
  hours, cafeteria menus, event registration), use "no_op".
- Return ONLY the JSON array.  No markdown fences, no extra text.
"""

# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


async def interpret_notes(operator_notes: list[str]) -> list[dict[str, Any]]:
    """Call the LLM and return raw directive interpretation dicts.

    Retries once on transient JSON-parse failure and attempts lightweight
    repair (fence stripping + array extraction) before giving up.
    """
    settings = get_settings()

    user_content = "Interpret these operator notes:\n\n"
    for idx, note in enumerate(operator_notes):
        user_content += f"[{idx}] {note}\n"

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    raw_text: str = ""
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
                resp = await client.post(
                    f"{settings.llm_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()

            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"].strip()

            try:
                parsed = _try_parse_json_array(raw_text)
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(
                    "LLM returned malformed JSON on attempt %d: %s",
                    attempt,
                    exc,
                )
                continue

            if not isinstance(parsed, list):
                raise TypeError(
                    f"LLM returned {type(parsed).__name__}, expected list"
                )

            return parsed  # type: ignore[no-any-return]
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            last_error = exc
            logger.warning(
                "LLM call failed on attempt %d: %s", attempt, exc
            )
            if attempt == 2:
                raise

    raise ValueError(
        f"LLM returned invalid JSON after 2 attempts: {last_error}. "
        f"Last payload: {raw_text[:200]!r}"
    )


def _try_parse_json_array(raw_text: str) -> Any:
    """Parse ``raw_text`` as a JSON array, with two repair fallbacks."""
    cleaned = raw_text.strip()

    # Strip markdown fences (```json ... ``` or ``` ... ```)
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [
            l for l in lines if not l.strip().startswith("```")
        ]
        cleaned = "\n".join(lines).strip()

    # Fast path: valid JSON
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Repair path 1: grab the first JSON array substring
    match = _JSON_ARRAY_RE.search(cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Repair path 2: drop trailing commas before } or ]
    repaired = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return json.loads(repaired)


# ---------------------------------------------------------------------------
# Conversion to Pydantic models
# ---------------------------------------------------------------------------

_DIRECTIVE_TYPE_MAP: dict[str, DirectiveType] = {
    "solar_reduction": DirectiveType.SOLAR_REDUCTION,
    "minimum_battery_reserve": DirectiveType.MINIMUM_BATTERY_RESERVE,
    "no_charge_window": DirectiveType.NO_CHARGE_WINDOW,
    "no_discharge_window": DirectiveType.NO_DISCHARGE_WINDOW,
    "max_grid_window": DirectiveType.MAX_GRID_WINDOW,
    "no_op": DirectiveType.NO_OP,
}


def _parse_adjustment(
    raw: dict[str, Any] | None,
    dtype: DirectiveType,
) -> StructuredAdjustment | None:
    """Parse the raw adjustment dict into a StructuredAdjustment."""
    if raw is None or dtype == DirectiveType.NO_OP:
        return None

    return StructuredAdjustment(
        hours=raw.get("hours"),
        factor=raw.get("factor"),
        minimum_energy_kwh=raw.get("minimum_energy_kwh"),
        max_grid_kwh=raw.get("max_grid_kwh"),
    )


def to_directive_interpretations(
    raw_list: list[dict[str, Any]],
) -> list[DirectiveInterpretation]:
    """Convert raw LLM dicts into typed DirectiveInterpretation models."""
    results: list[DirectiveInterpretation] = []
    for raw in raw_list:
        dtype_str = raw.get("directive_type", "no_op")
        dtype = _DIRECTIVE_TYPE_MAP.get(dtype_str, DirectiveType.NO_OP)

        results.append(
            DirectiveInterpretation(
                note_index=int(raw.get("note_index", len(results))),
                applies=bool(raw.get("applies", dtype != DirectiveType.NO_OP)),
                directive_type=dtype,
                structured_adjustment=_parse_adjustment(
                    raw.get("structured_adjustment"), dtype
                ),
                explanation=raw.get("explanation", ""),
            )
        )
    return results
