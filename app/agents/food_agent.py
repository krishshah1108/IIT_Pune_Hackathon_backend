"""Food / meal-timing agent (Gemini `generateContent` only)."""

from __future__ import annotations

from typing import Any

from app.agents.base import Agent
from app.agents.gemini_client import GeminiTextClient
from app.agents.gemini_enrichment import run_gemini_enrichment

_FOOD_SYSTEM = """You are a patient-facing assistant for food, drinks, and meal timing with medicines.
Use ONLY the structured medicine data provided (names and any instructions on the prescription).
Output a single JSON object, no markdown fences, no extra text.
Schema: {"status":"ok","items":[{"name":"string","advice":"string"}],"confidence":0.0-1.0}
Rules:
- One item per medicine; match "name" to input names.
- Each "advice" must cover, in plain language:
  (1) take with food, on an empty stomach, or either — whichever fits this drug class;
  (2) what to avoid or separate in time: e.g. calcium/iron/dairy or antacids with thyroid medicines (e.g. levothyroxine/Thyronorm:
  not with tea/coffee/milk; wait ~30–60 min after these before the dose, or as local guidance says);
  (3) vitamin K–rich foods (e.g. leafy greens like palak) and warfarin: keep intake consistent, do not suddenly change greens — never give a specific dose change;
  (4) alcohol or grapefruit only if class-relevant, otherwise say "ask if unsure".
- Do NOT repeat reminder clock times or paraphrase "take at 08:00" — focus on food/drink interactions.
- If instructions field hints at with/after food, align with that.
- Stay conservative; say ask pharmacist/doctor when unclear."""

_FOOD_USER = """Language hint for tone: {language}

Medicines (JSON array):
{meds_json}

Return JSON only."""


class FoodAgent(Agent):
    """Meal-related advice per medicine via Gemini only."""

    def __init__(self, gemini: GeminiTextClient | None = None) -> None:
        self._gemini = gemini if gemini is not None else GeminiTextClient()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await run_gemini_enrichment(
            self._gemini,
            payload,
            system=_FOOD_SYSTEM,
            user_template=_FOOD_USER,
            value_key="advice",
            log_name="food_agent.gemini_failed",
            max_confidence=0.93,
            default_conf=0.8,
        )
