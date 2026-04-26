# MediReminder Backend

Production-oriented FastAPI backend for AI-powered medicine reminder workflows.

## Stack
- Python 3.11+
- FastAPI (async)
- MongoDB + Motor
- Pydantic v2
- Async background worker + event-driven orchestrator

## Folder structure (key pieces)
```text
app/
 ├── api/              # FastAPI routes and dependencies
 ├── orchestrator/   # `OrchestratorEngine` — dispatches `prescription_uploaded`, `dose_missed`, `alert_required`
 ├── agents/         # `VisionAgent` (Gemini vision), `LiteracyAgent` + `FoodAgent` (Gemini), shared `gemini_enrichment.py`
 ├── services/       # Business services (prescriptions, OTP, alerts, …)
 ├── repositories/   # Mongo data access
 ├── core/           # Config, DB, JWT, logging
 └── workers/        # e.g. missed-dose poller
```

Prescription draft: **Gemini vision** runs first, then **literacy** and **food** run in order (not parallel). A shared helper builds prompts from `medicine_context` and normalizes structured JSON output.

## Setup
1. Create virtualenv and install dependencies:
   - `pip install -r requirements.txt`
2. Create environment file (e.g. `copy .env.example .env` on Windows) and set **MongoDB**, **SMTP**, **Cloudinary**, and **Gemini** (`GOOGLE_API_KEY`, `GEMINI_API_BASE_URL`, `GEMINI_VISION_MODEL`, `GEMINI_LITERACY_MODEL`, `GEMINI_FOOD_MODEL`, `GEMINI_TIMEOUT_SECONDS`, …). Without a Gemini key, AI blocks return `status: "failed"` with an `error` code.
3. Run app:
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

## Event Pipeline
- `prescription_uploaded` — used for **idempotent** event logging; the heavy Vision/Literacy/Food work for uploads runs **inline** on **`POST /prescriptions/upload`** (same request), then the user calls **`POST /prescriptions/{id}/confirm`** to write medicines + dose logs.
- `dose_missed`
- `alert_required`

## Caregivers (CRUD)
Authenticated users (JWT) can manage **multiple caregivers** via **`GET/POST /caregivers`**, **`GET/PATCH/DELETE /caregivers/{caregiver_id}`** — see **`api_docs.md`**. Each caregiver has **`display_name`**, **`email`**, optional **`phone`** / **`relationship_label`**, logical flags **`is_active`** (pause without delete) and **`notify_on_missed_dose`** (placeholder for a future **missed-dose → notify caregiver** flow), and **soft delete** on **`DELETE`**. Email is unique per user among non-deleted rows; Mongo has a **partial unique index** on (`user_id`, `email`).

Idempotency is enforced via the `events` collection using unique event IDs.

## Prescription flow (frontend)

1. **`POST /auth/otp/verify`** → store **`access_token`**.
1b. (Optional) **`GET/POST/PATCH/DELETE /caregivers`…** to register contacts for **future** missed-dose notifications.
2. **`POST /prescriptions/upload`** (multipart: `language`, `image` + **`Authorization: Bearer`**) — blocks until Gemini vision + literacy + food finish. Response includes `analysis` (`vision`, `literacy`, `food`). Vision must succeed with at least one medicine, else prescription status is `failed`.
3. User reviews/edits → **`POST /prescriptions/{prescription_id}/confirm`** with `{ "medicines": null }` to accept the draft, or send an edited **`medicines`** array (optional per-row **`reminder_times_24h`**; must be valid **`HH:MM`**).
4. Dose logs exist only after step 3 → use **`POST /doses/log`** for adherence.

**Client timeouts:** set generous read timeout on upload (`GEMINI_TIMEOUT_SECONDS` applies to Gemini calls).

**Connection refused:** the app URL in your client must match where Uvicorn listens (e.g. if the API runs in Docker, `localhost` from another container is wrong — use the service hostname or host port mapping).

## Example Requests

### Request OTP
`POST /auth/otp/request`
```json
{
  "email": "patient@example.com"
}
```

### Verify OTP
`POST /auth/otp/verify`
```json
{
  "email": "patient@example.com",
  "otp": "123456"
}
```
Response includes **`access_token`** and **`token_type`**: `"bearer"`. Use **`Authorization: Bearer <access_token>`** on **`PATCH /users/profile`**, **`POST /prescriptions/*`**, and **`POST /doses/log`**.

### Dose Log Update
`POST /doses/log` — **requires** `Authorization: Bearer <access_token>` (dose log must belong to that user).

```json
{
  "dose_log_id": "dose_abc12345",
  "status": "taken",
  "taken_at": "2026-04-24T08:00:00Z"
}
```

## Notes
- **Vision:** Gemini vision model extracts `medicines[]` from the prescription image with structured JSON output.
- **Literacy + food:** Implemented via `app/agents/gemini_enrichment.py` (shared pipeline: serialize medicines -> Gemini -> parse JSON). If vision fails or has no medicines, these steps are skipped.
- SMTP uses real `smtplib` with async thread offload.
- **Missed-dose** path: check-in and triage agents isolate failures for **`dose_missed`** events.

## API payloads

For complete JSON request/response examples (including multiple success/error variants for caregivers and prescriptions), see `api_docs.md`.
