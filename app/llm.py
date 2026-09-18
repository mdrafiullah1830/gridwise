"""LLM integration for operator-note interpretation.

Uses an OpenAI-compatible chat completions endpoint with retry + cache.
Falls back to deterministic keyword parsing when LLM is unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
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

_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)

# ---------------------------------------------------------------------------
# In-memory LLM response cache (keyed by note hash)
# ---------------------------------------------------------------------------
_cache: dict[str, list[dict[str, Any]]] = {}


def _cache_key(notes: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(notes)).encode()).hexdigest()[:16]


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
# Keyword-based fallback parser (no LLM needed)
# ---------------------------------------------------------------------------

_HOUR_RE = re.compile(r"(\d{1,2})\s*(?:AM|PM|am|pm)", re.IGNORECASE)
_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:to|until|till|-)\s*(\d{1,2})\s*(?:AM|PM|am|pm)?", re.IGNORECASE)


def _parse_hour_from_text(text: str) -> int | None:
    """Extract hour from text like '2 PM', '14:00', 'noon', 'midnight'."""
    low = text.lower().strip()
    if low in ("noon", "12 pm", "12pm", "12:00 pm"):
        return 12
    if low in ("midnight", "12 am", "12am", "00:00"):
        return 0
    m = _HOUR_RE.search(text)
    if m:
        h = int(m.group(1))
        if "pm" in text.lower() and h != 12:
            h += 12
        if "am" in text.lower() and h == 12:
            h = 0
        return h % 24
    return None


def _extract_hours_from_note(note: str) -> list[int] | None:
    """Extract hour range from operator note."""
    low = note.lower()

    # Check for range patterns like "noon until 2 PM", "1 PM to 3 PM"
    range_match = _RANGE_RE.search(note)
    if range_match:
        start = _parse_hour_from_text(range_match.group(1) + (" PM" if int(range_match.group(1)) < 12 else ""))
        end = _parse_hour_from_text(range_match.group(2) + (" PM" if int(range_match.group(2)) < 12 else ""))
        if start is not None and end is not None:
            hours = list(range(start, end)) if end > start else list(range(start, 24)) + list(range(end))
            return hours

    # Check for "noon until X PM" pattern
    if "noon" in low:
        end_match = re.search(r"noon\s+(?:until|to|till|-)\s*(\d{1,2})\s*(?:PM|pm)?", note)
        if end_match:
            end_h = int(end_match.group(1))
            if end_h < 12:
                end_h += 12
            return list(range(12, end_h))

    # Check for "from X to Y" with hours
    from_match = re.search(r"(\d{1,2})\s*(?:AM|PM|am|pm)?\s+(?:to|until|till|-)\s+(\d{1,2})\s*(?:AM|PM|am|pm)", note)
    if from_match:
        start = _parse_hour_from_text(from_match.group(1) + (" AM" if "am" in note.lower() else " PM"))
        end = _parse_hour_from_text(from_match.group(2) + (" PM" if "pm" in note.lower() else " AM"))
        if start is not None and end is not None:
            return list(range(start, end))

    # Check for specific hour mentions like "from 01:00 to 06:00"
    time_match = re.search(r"(\d{1,2}):00\s+(?:to|until|till|-)\s+(\d{1,2}):00", note)
    if time_match:
        start = int(time_match.group(1))
        end = int(time_match.group(2))
        return list(range(start, end))

    return None


def _fallback_parse(notes: list[str]) -> list[dict[str, Any]]:
    """Deterministic keyword-based fallback when LLM is unavailable."""
    results = []
    for idx, note in enumerate(notes):
        low = note.lower().strip()

        # Solar reduction patterns
        if any(kw in low for kw in ("solar", "panel", "wash", "cleaning", "clean")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = [12, 13]  # default noon-2pm
            # Try to extract factor
            factor = 0.25
            pct_match = re.search(r"(\d+)\s*%", note)
            if pct_match:
                pct = int(pct_match.group(1))
                factor = (100 - pct) / 100.0
            elif "roughly 25%" in low or "25%" in low:
                factor = 0.25
            elif "no solar" in low or "zero solar" in low:
                factor = 0.0
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": hours, "factor": factor},
                "explanation": f"Solar reduced to {factor*100:.0f}% during hours {hours}."
            })
            continue

        # Minimum battery reserve patterns
        if any(kw in low for kw in ("battery", "reserve", "soc", "charge level", "above", "keep")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = list(range(24))
            # Try to extract kWh or percentage
            kwh_match = re.search(r"(\d+)\s*kwh", low)
            pct_match = re.search(r"(\d+)\s*%", low)
            if kwh_match:
                min_kwh = float(kwh_match.group(1))
            elif pct_match:
                min_kwh = float(pct_match.group(1)) * 2.2  # rough 220kWh capacity
            else:
                min_kwh = 66.0  # 30% of 220
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": hours, "minimum_energy_kwh": min_kwh},
                "explanation": f"Battery reserve of {min_kwh} kWh maintained during hours {hours}."
            })
            continue

        # No charge window patterns
        if any(kw in low for kw in ("avoid charging", "no charge", "don't charge", "do not charge", "stop charging")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = [17, 18, 19, 20]
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": hours},
                "explanation": f"Battery charging disabled during hours {hours}."
            })
            continue

        # No discharge window patterns
        if any(kw in low for kw in ("avoid discharging", "no discharge", "don't discharge", "do not discharge")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = list(range(24))
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {"hours": hours},
                "explanation": f"Battery discharging disabled during hours {hours}."
            })
            continue

        # Max grid window patterns
        if any(kw in low for kw in ("grid import", "grid should not", "grid cap", "max grid", "exceed")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = list(range(24))
            kwh_match = re.search(r"(\d+)\s*kwh", low)
            max_kwh = float(kwh_match.group(1)) if kwh_match else 60.0
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": hours, "max_grid_kwh": max_kwh},
                "explanation": f"Grid capped at {max_kwh} kWh during hours {hours}."
            })
            continue

        # Discharge scheduling patterns
        if any(kw in low for kw in ("schedule battery", "power the load", "discharge from", "use battery")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = [21, 22, 23, 0, 1, 2, 3, 4]
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": hours},
                "explanation": f"Battery scheduled to discharge during hours {hours} — no charging allowed."
            })
            continue

        # Charge scheduling patterns
        if any(kw in low for kw in ("charge by", "charge before", "fully charged", "charge to full")):
            hours = _extract_hours_from_note(note)
            if hours is None:
                hours = list(range(6, 12))
            results.append({
                "note_index": idx, "applies": True,
                "directive_type": "no_discharge_window",
                "structured_adjustment": {"hours": hours},
                "explanation": f"Battery charging during hours {hours} — no discharging allowed."
            })
            continue

        # Default: no_op
        results.append({
            "note_index": idx, "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Note does not affect energy schedule."
        })

    return results


# ---------------------------------------------------------------------------
# LLM call with retry + backoff
# ---------------------------------------------------------------------------


async def interpret_notes(operator_notes: list[str]) -> list[dict[str, Any]]:
    """Call the LLM with retry, cache, and fallback.

    1. Check cache first
    2. Try LLM with 3 retries + exponential backoff
    3. Fall back to deterministic keyword parser
    """
    settings = get_settings()
    key = _cache_key(operator_notes)

    # Cache hit
    if key in _cache:
        logger.info("LLM cache hit for key=%s", key)
        return _cache[key]

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

    # Retry with exponential backoff: 2s, 4s, 8s
    for attempt in range(1, 4):
        try:
            delay = 2 ** attempt  # 2, 4, 8 seconds
            if attempt > 1:
                logger.info("LLM retry %d/3 after %ds delay", attempt, delay)
                await asyncio.sleep(delay)

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
                logger.warning("LLM JSON parse error on attempt %d: %s", attempt, exc)
                continue

            if not isinstance(parsed, list):
                raise TypeError(f"LLM returned {type(parsed).__name__}, expected list")

            # Cache successful response
            _cache[key] = parsed
            logger.info("LLM call success, cached key=%s", key)
            return parsed  # type: ignore[no-any-return]

        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code == 429:
                logger.warning("LLM rate limited (429) on attempt %d", attempt)
                continue
            logger.warning("LLM HTTP error on attempt %d: %s", attempt, exc)
            if attempt == 3:
                break
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            last_error = exc
            logger.warning("LLM call failed on attempt %d: %s", attempt, exc)
            if attempt == 3:
                break

    # All LLM attempts failed — use fallback parser
    logger.warning("LLM unavailable after 3 attempts (%s), using fallback parser", last_error)
    return _fallback_parse(operator_notes)


def _try_parse_json_array(raw_text: str) -> Any:
    """Parse ``raw_text`` as a JSON array, with two repair fallbacks."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = _JSON_ARRAY_RE.search(cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

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
