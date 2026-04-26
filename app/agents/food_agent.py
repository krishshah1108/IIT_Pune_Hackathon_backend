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
- Audience is elderly patients. Keep words very simple and easy to read.
- Each "advice" must be ONLY 2-3 short bullet points total (max ~300 characters).
- Start each line with "- " (dash + space).
- Format bullets with clear labels:
  Bullet 1 starts with: "- Eat:"
  Bullet 2 starts with: "- Avoid:"
  Optional bullet 3 starts with: "- Note:"
- Include what to eat/okay and what to avoid/separate in time.
- Mention alcohol/grapefruit only if relevant; otherwise keep it general and short.
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
