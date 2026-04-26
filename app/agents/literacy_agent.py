"""Medicine literacy agent (Gemini `generateContent` only)."""

from __future__ import annotations

from typing import Any

from app.agents.base import Agent
from app.agents.gemini_client import GeminiTextClient
from app.agents.gemini_enrichment import run_gemini_enrichment

_LIT_SYSTEM = """You are a patient education assistant. Use the medicine names and fields from the JSON only.
Output a single JSON object, no markdown fences, no extra text.
Schema: {"status":"ok","items":[{"name":"string","explanation":"string"}],"confidence":0.0-1.0}
Rules:
- One item per medicine in the input list; match "name" to each input name.
- Each "explanation" must answer WHY this medicine is typically prescribed: what class it is, what it does in simple terms
  (e.g. reduces acid, relieves pain/fever, treats infection), in 2–4 short sentences.
- Do NOT repeat dosage schedule, reminder times, or "take at 8 AM" style instructions — the app already shows that elsewhere.
- Do NOT invent a diagnosis for this patient; you may say "often used for …" in general terms only.
- End with one line: follow prescriber/pharmacist for this specific case.
- If the name is ambiguous or unknown, say what is known cautiously and lower confidence."""

_LIT_USER = """Language hint for tone (BCP-47 or short code): {language}

Medicines (JSON array; use only these fields for context, do not copy schedule into the explanation):
{meds_json}

Return JSON only."""


class LiteracyAgent(Agent):
    """Patient-friendly literacy lines per medicine via Gemini only."""

    def __init__(self, gemini: GeminiTextClient | None = None) -> None:
        self._gemini = gemini if gemini is not None else GeminiTextClient()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await run_gemini_enrichment(
            self._gemini,
            payload,
            system=_LIT_SYSTEM,
            user_template=_LIT_USER,
            value_key="explanation",
            log_name="literacy_agent.gemini_failed",
            max_confidence=0.95,
            default_conf=0.82,
        )
