# MediReminder — HTTP API Reference

This document describes the **MediReminder** FastAPI backend for frontend integration.

**Interactive docs (same server):** `GET /docs` (Swagger UI) and `GET /redoc` (ReDoc).

---

## Base URL

| Environment | Example base URL |
|---------------|------------------|
| Local default | `http://localhost:8000` |
| Production | Configure per deployment |

All paths below are **relative** to the base URL (e.g. `POST /auth/otp/request` → `http://localhost:8000/auth/otp/request`).

**Default content type for JSON bodies:** `Content-Type: application/json` unless noted otherwise.

---

## Authentication model (important for frontend)

MediReminder uses **email-only OTP**. There is **no** separate “signup” and “login” endpoint:

| User state | What happens on successful OTP verify |
|------------|----------------------------------------|
| Email never seen before | User record is **created** (`is_new_user: true`) |
| Email already exists | User is **signed in** (`is_new_user: false`), `last_login_at` updated |

After OTP verification, the client receives an **`access_token`** (JWT) and must send it on **protected** routes (see below). Persist **`access_token`**, **`user.user_id`**, and **`user.email`** as appropriate for your client. Optional **`first_name`** and **`last_name`** default to empty strings at signup; set them with **`PATCH /users/profile`** after login (token required).

---

## Current API security (read this)

### Bearer JWT (after OTP verify)

On successful **`POST /auth/otp/verify`**, the JSON includes **`access_token`** (string) and **`token_type`** (`"bearer"`). Send the token on every **protected** request:

```http
Authorization: Bearer <access_token>
```

| Protected route | Extra rules |
|-----------------|-------------|
| **`PATCH /users/profile`** | User identity comes from the JWT (`sub` = `user_id`). Body is only name fields. |
| **`/caregivers` …** | All caregiver routes require JWT. Caregivers belong to the token’s **`user_id`** (`sub`); no cross-user access. |
| **`POST /prescriptions/upload`** | JWT required. **Waits** for Vision + Literacy + Food; response includes **`analysis`** draft. **No** medicines/doses in DB until **`confirm`**. |
| **`POST /prescriptions/{prescription_id}/confirm`** | JWT + ownership. Commits medicines + dose schedules (optional edited list in body). |
| **`POST /doses/log`** | JWT required. The dose log must belong to the token’s **`sub`** (`user_id`); otherwise update fails (**`404`**) like a missing log. |

**Not** protected (no `Authorization` header): **`GET /health`**, **`POST /auth/otp/request`**, **`POST /auth/otp/resend`**, **`POST /auth/otp/verify`**.

**Token contents (HS256):** claims include **`sub`** (user id), **`email`**, **`type`**: `"access"`, **`iat`**, **`exp`**. Lifetime is configured by **`JWT_ACCESS_EXPIRE_MINUTES`** (default 7 days for hackathon convenience). **Set a strong `JWT_SECRET_KEY` in production.**

There is **no** refresh-token flow in this codebase; when the access token expires, the user runs OTP again.

---

## Verification log (manual QA)

The following were **executed successfully** against a local instance with valid `.env` (MongoDB + SMTP + Cloudinary as applicable):

| Area | Date (UTC) | Result |
|------|------------|--------|
| `POST /auth/otp/request` | 2026-04-24 | `200`, OTP flow OK |
| `POST /auth/otp/resend` | 2026-04-24 | `200` after cooldown; `404` / `409` when misused |
| `POST /auth/otp/verify` (new user) | 2026-04-24 | `200`, `is_new_user: true` |
| `POST /auth/otp/verify` (reuse OTP) | 2026-04-24 | `401`, `OTP already used` |
| `GET /health` | 2026-04-24 | `200`, `{"status":"ok"}` |

**Re-run locally (optional):**

```bash
# From repo root, with .env configured and PYTHONPATH set
set PYTHONPATH=.
.myenv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from app.main import app; \
from unittest.mock import patch; \
email='your-test@example.com'; \
with TestClient(app) as c, patch('app.services.otp_service.generate_otp', return_value='424242'): \
  print(c.post('/auth/otp/request', json={'email': email}).status_code, c.post('/auth/otp/request', json={'email': email}).json()); \
  print(c.post('/auth/otp/verify', json={'email': email, 'otp': '424242'}).json())"
```

*(Use a fresh email each run, or you will hit cooldown / “OTP already used”.)*

---

## Common HTTP status codes

| Code | Meaning | Typical cause |
|------|---------|----------------|
| `200` | Success | Normal response |
| `400` | Bad request | Invalid multipart / image type / empty file / confirm body invalid / Cloudinary validation |
| `401` | Unauthorized | Missing/invalid JWT on protected routes; OTP invalid, expired, already used, max attempts |
| `404` | Not found | OTP resend with no prior session; user missing for JWT `sub` (`/prescriptions/upload`); prescription not found / wrong owner; dose log missing or not owned by user; caregiver not found for **`/caregivers/{id}`** |
| `409` | Conflict | OTP resend after session already verified; duplicate prescription image; confirm called in wrong **`status`** (not `awaiting_confirmation`); duplicate caregiver **email** for the same user (**`POST/PATCH /caregivers`**) |
| `422` | Validation error | JSON/form field failed Pydantic validation |
| `429` | Too many requests | OTP throttling / resend cooldown (see Auth section) |

**Error body shape (FastAPI):**

```json
{ "detail": "Human-readable message" }
```

For `422`, `detail` may be a **list** of validation errors (see FastAPI docs).

---

## Endpoints overview

| Method | Path | Summary |
|--------|------|---------|
| `GET` | `/health` | Liveness |
| `POST` | `/auth/otp/request` | Send OTP to email |
| `POST` | `/auth/otp/resend` | Resend OTP (active unverified session only; same limits as request) |
| `POST` | `/auth/otp/verify` | Verify OTP → create or login user |
| `GET` | `/users/profile` | Get current user profile (**Bearer JWT**) |
| `PATCH` | `/users/profile` | Update optional `first_name` / `last_name` (**Bearer JWT**) |
| `GET` | `/caregivers` | List caregivers for the current user (**Bearer JWT**) |
| `POST` | `/caregivers` | Add a caregiver (**Bearer JWT**) |
| `GET` | `/caregivers/{caregiver_id}` | Get one caregiver (**Bearer JWT**) |
| `PATCH` | `/caregivers/{caregiver_id}` | Update caregiver fields (**Bearer JWT**) |
| `DELETE` | `/caregivers/{caregiver_id}` | Soft-delete a caregiver (**Bearer JWT**) |
| `POST` | `/prescriptions/upload` | Multipart image → Cloudinary → **sync** AI draft in response (**Bearer JWT**) |
| `POST` | `/prescriptions/{prescription_id}/confirm` | Save medicines + dose schedules after user review (**Bearer JWT**) |
| `POST` | `/doses/log` | Update dose adherence (**Bearer JWT**; log must belong to user) |
| `GET` | `/doses/calendar` | Month summary for calendar UI (**Bearer JWT**) |
| `GET` | `/doses/day` | Selected-day dose list (**Bearer JWT**) |

---

## 1. Health

### `GET /health`

**Purpose:** Simple readiness / liveness check (no database logic).

**Headers:** none required.

**Query:** none.

**Body:** none.

#### Example request

```http
GET /health HTTP/1.1
Host: localhost:8000
```

#### Example success response — `200 OK`

```json
{
  "status": "ok"
}
```

---

## 2. Authentication (OTP)

### 2.1 `POST /auth/otp/request`

**Purpose:** Start authentication. Sends a numeric OTP to the given email (SMTP). Creates a new OTP session in MongoDB.

**Headers:**

| Header | Required | Value |
|--------|----------|--------|
| `Content-Type` | Yes | `application/json` |

**Body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string (email) | Yes | Valid email address |

**Query:** none.

#### Example request body

```json
{
  "email": "patient@example.com"
}
```

#### Example success response — `200 OK`

```json
{
  "success": true,
  "message": "OTP sent",
  "resend_after_seconds": 60
}
```

`resend_after_seconds` comes from server config (`OTP_RESEND_COOLDOWN_SECONDS`).

#### Error responses

| Status | `detail` (example) | When |
|--------|-------------------|------|
| `422` | Validation (invalid email format) | Pydantic `EmailStr` failed |
| `429` | `Too many OTP requests...` | Hourly cap (`OTP_REQUESTS_PER_HOUR`) |
| `429` | `OTP recently sent. Retry after N seconds.` | Resend cooldown (`OTP_RESEND_COOLDOWN_SECONDS`) |

---

### 2.2 `POST /auth/otp/resend`

**Purpose:** Send a **new** OTP email while the user is still on the OTP entry screen. Only allowed when the **latest** OTP session for that email exists and is **not yet verified** (same email flow as `otp/request`). Use this for “Didn’t get the code?” instead of calling `otp/request` again, which would hit the same cooldown anyway but is semantically clearer for the UI.

**Behavior (summary):**

- Same **hourly cap** and **resend cooldown** as `POST /auth/otp/request` (see §2.1).
- After a successful resend, **`POST /auth/otp/verify`** must use the **new** code (latest session wins).

**Headers / body:** Same as §2.1 (`Content-Type: application/json`, body `{ "email": "..." }`).

#### Example success response — `200 OK`

```json
{
  "success": true,
  "message": "OTP resent",
  "resend_after_seconds": 60
}
```

#### Error responses

| Status | `detail` (example) | When |
|--------|-------------------|------|
| `422` | Validation (invalid email) | Pydantic `EmailStr` failed |
| `404` | `No OTP session found...` | No `otp/request` (or no session row) for that email |
| `409` | `OTP already verified...` | Latest session already consumed; start over with `otp/request` |
| `429` | `Too many OTP requests...` | Hourly cap |
| `429` | `OTP recently sent. Retry after N seconds.` | Cooldown not elapsed |

---

### 2.3 `POST /auth/otp/verify`

**Purpose:** Verify OTP. If valid: marks session used, **creates user if new** else **updates login**, returns **`user`** and a new **`access_token`** (JWT) for protected APIs.

**Headers:**

| Header | Required | Value |
|--------|----------|--------|
| `Content-Type` | Yes | `application/json` |

**Body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string (email) | Yes | Same email as OTP request |
| `otp` | string | Yes | **Digits only**, length 4–8 (typically 6) |

**Query:** none.

**Response:** Includes **`access_token`** and **`token_type`** (`"bearer"`). Use the token as `Authorization: Bearer …` on **`/users/profile`**, **`/caregivers`**, **`POST /prescriptions/upload`**, **`POST /prescriptions/{id}/confirm`**, and **`/doses/log`**.

#### Example request body

```json
{
  "email": "patient@example.com",
  "otp": "123456"
}
```

#### Example success response — `200 OK` (new user)

```json
{
  "success": true,
  "message": "Authenticated",
  "is_new_user": true,
  "user": {
    "user_id": "usr_cb7090dcc01944bbb7bde6dda0be7b19",
    "email": "patient@example.com",
    "first_name": "",
    "last_name": "",
    "last_login_at": "2026-04-24T16:02:08.410919Z"
  },
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.…",
  "token_type": "bearer"
}
```

#### Example success response — `200 OK` (returning user)

Same shape with `"is_new_user": false` and updated `last_login_at`, and a **new** `access_token` each successful verify. `first_name` / `last_name` are always present (default `""` until set via **`PATCH /users/profile`**).

#### Error responses

| Status | `detail` (examples) | When |
|--------|---------------------|------|
| `422` | OTP must be numeric / length | Invalid `otp` format |
| `401` | `OTP session not found` | No prior `otp/request` / resend for email |
| `401` | `OTP expired` | Past `expires_at` |
| `401` | `Invalid OTP` | Wrong code (attempt counter incremented) |
| `401` | `Max OTP attempts exceeded` | Too many wrong tries |
| `401` | `OTP already used` | Successful verify already done for that session |

---

## 3. User profile

### `GET /users/profile`

**Purpose:** Fetch current user profile for dashboard/account screens.

**Authentication:** **`Authorization: Bearer <access_token>`** from **`POST /auth/otp/verify`**.

**Headers:**

| Header | Required | Value |
|--------|----------|--------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Query:** none.

#### Example success response — `200 OK`

```json
{
  "user_id": "usr_cb7090dcc01944bbb7bde6dda0be7b19",
  "email": "patient@example.com",
  "first_name": "Priya",
  "last_name": "Sharma",
  "last_login_at": "2026-04-24T16:02:08.410919Z"
}
```

#### Error responses

| Status | `detail` (example) | When |
|--------|-------------------|------|
| `401` | `Not authenticated` / `Token expired` / `Invalid or expired token` | Missing `Authorization`, bad JWT, or expired |
| `404` | `User not found` | JWT `sub` does not match an active user |

### `PATCH /users/profile`

**Purpose:** Update **`first_name`** and/or **`last_name`** after the user exists (OTP verify). This is **not** part of signup/login. Names are optional on the user record and default to empty strings.

**Authentication:** **`Authorization: Bearer <access_token>`** from **`POST /auth/otp/verify`**. The user is identified by the JWT’s **`sub`** claim (`user_id`); do **not** send `email` in the body.

**Headers:**

| Header | Required | Value |
|--------|----------|--------|
| `Authorization` | Yes | `Bearer <access_token>` |
| `Content-Type` | Yes | `application/json` |

**Body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `first_name` | string | No | Display name; max 120 chars; trimmed. Omit to leave unchanged; send `""` to clear. |
| `last_name` | string | No | Same as `first_name`. |

If both are omitted, the request succeeds with no field updates (still returns current profile).

#### Example request body

```json
{
  "first_name": "Priya",
  "last_name": "Sharma"
}
```

#### Example success response — `200 OK`

```json
{
  "success": true,
  "message": "Profile updated",
  "user_id": "usr_cb7090dcc01944bbb7bde6dda0be7b19",
  "email": "patient@example.com",
  "first_name": "Priya",
  "last_name": "Sharma",
  "last_login_at": "2026-04-24T16:02:08.410919Z"
}
```

#### Error responses

| Status | `detail` (example) | When |
|--------|-------------------|------|
| `401` | `Not authenticated` / `Token expired` / `Invalid or expired token` | Missing `Authorization`, bad JWT, or expired |
| `422` | Validation | Invalid name length |
| `404` | `User not found` | JWT `sub` does not match an active user (rare) |

### Caregivers (CRUD)

A logged-in patient can register multiple caregivers. Ownership is strict: all caregiver rows are scoped to JWT `sub`.

#### `GET /caregivers?include_inactive=false`

**Success (`200`)**
```json
{
  "success": true,
  "items": [
    {
      "caregiver_id": "cgr_15fdc5d7f8f1494fa1f4d6573f96889a",
      "user_id": "usr_7ada3060debe4bbeaa83a395891281f8",
      "display_name": "Rahul Sharma",
      "email": "rahul@example.com",
      "phone": "+91-9876543210",
      "relationship_label": "Brother",
      "is_active": true,
      "notify_on_missed_dose": true,
      "created_at": "2026-04-25T09:10:21.202000",
      "updated_at": "2026-04-25T09:10:21.202000"
    }
  ]
}
```

#### `POST /caregivers`

**Request body**
```json
{
  "display_name": "Rahul Sharma",
  "email": "rahul@example.com",
  "phone": "+91-9876543210",
  "relationship_label": "Brother",
  "is_active": true,
  "notify_on_missed_dose": true
}
```

**Success (`201`)**
```json
{
  "success": true,
  "item": {
    "caregiver_id": "cgr_15fdc5d7f8f1494fa1f4d6573f96889a",
    "user_id": "usr_7ada3060debe4bbeaa83a395891281f8",
    "display_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "phone": "+91-9876543210",
    "relationship_label": "Brother",
    "is_active": true,
    "notify_on_missed_dose": true,
    "created_at": "2026-04-25T09:10:21.202000",
    "updated_at": "2026-04-25T09:10:21.202000"
  }
}
```

**Duplicate email (`409`)**
```json
{ "detail": "Caregiver with this email already exists" }
```

#### `GET /caregivers/{caregiver_id}`

**Success (`200`)**
```json
{
  "success": true,
  "item": {
    "caregiver_id": "cgr_15fdc5d7f8f1494fa1f4d6573f96889a",
    "user_id": "usr_7ada3060debe4bbeaa83a395891281f8",
    "display_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "phone": "+91-9876543210",
    "relationship_label": "Brother",
    "is_active": true,
    "notify_on_missed_dose": true,
    "created_at": "2026-04-25T09:10:21.202000",
    "updated_at": "2026-04-25T09:10:21.202000"
  }
}
```

**Not found / wrong owner / deleted (`404`)**
```json
{ "detail": "Caregiver not found" }
```

#### `PATCH /caregivers/{caregiver_id}`

**Request body (partial update)**
```json
{
  "display_name": "Rahul S.",
  "notify_on_missed_dose": false
}
```

**Success (`200`)**
```json
{
  "success": true,
  "item": {
    "caregiver_id": "cgr_15fdc5d7f8f1494fa1f4d6573f96889a",
    "user_id": "usr_7ada3060debe4bbeaa83a395891281f8",
    "display_name": "Rahul S.",
    "email": "rahul@example.com",
    "phone": "+91-9876543210",
    "relationship_label": "Brother",
    "is_active": true,
    "notify_on_missed_dose": false,
    "created_at": "2026-04-25T09:10:21.202000",
    "updated_at": "2026-04-25T09:30:45.501000"
  }
}
```

**Errors**
```json
{ "detail": "Caregiver not found" }
```
```json
{ "detail": "Caregiver with this email already exists" }
```

#### `DELETE /caregivers/{caregiver_id}`

**Success (`200`)**
```json
{
  "success": true,
  "message": "Caregiver deleted",
  "caregiver_id": "cgr_15fdc5d7f8f1494fa1f4d6573f96889a"
}
```

**Not found / already deleted (`404`)**
```json
{ "detail": "Caregiver not found" }
```

---

## 4. Prescriptions (upload → confirm)

**`POST /prescriptions/upload`** runs **Vision (Gemini vision model) → Literacy (Gemini) → Food (Gemini)** in the same HTTP request (after Cloudinary upload). Literacy runs before food (sequential). No medicines/dose logs are persisted until confirm.

**Draft medicine fields (under `analysis.vision.medicines[]`):** `name`, `dosage_pattern`, `duration_days`, `instructions`, `confidence`, optional **`name_legible`**, and **`reminder_times_24h`** (array of **`"HH:MM"`** strings in 24-hour format for app reminders — count should match daily frequency). If the model omits times, the server fills defaults from the dosage pattern.

**Status values (upload response `status`):**

| Status | Meaning |
|--------|---------|
| `processing` | Transient while agents run (usually not returned; you see `awaiting_confirmation` or `failed`) |
| `awaiting_confirmation` | Vision succeeded — **`analysis`** includes `vision` (and usually `literacy` / `food`; those may be `status: "failed"` if Gemini is missing or failed) |
| `failed` | Vision failed, no image, or no medicines extracted — see **`analysis.vision`** or top-level error |
| `confirmed` | Only after **`confirm`** (not returned from upload) |

**Timeouts:** Gemini calls use **`GEMINI_TIMEOUT_SECONDS`**; upload can be slow because all three model steps run inline.

**Order:** Vision once, then literacy once, then food once.

---

### `POST /prescriptions/upload`

**Purpose:** Cloudinary upload + **synchronous** multi-agent draft. Does **not** insert medicines/doses.

**Authentication:** **`Authorization: Bearer <access_token>`**.

**Headers:** `Authorization`, `Content-Type: multipart/form-data`.

**Body (form fields):** `language` (optional, 2–8 chars, default `en`), `image` (file, JPEG/PNG/WebP).

**Multipart example (`curl`)**
```bash
curl -X POST "http://localhost:8000/prescriptions/upload" \
  -H "Authorization: Bearer <access_token>" \
  -F "language=en" \
  -F "image=@uploads/23.jpg"
```

**Success — `200 OK` (shape):**

```json
{
  "success": true,
  "prescription_id": "prx_…",
  "event_id": "evt_…",
  "status": "awaiting_confirmation",
  "user_id": "usr_…",
  "language": "en",
  "image_url": "https://…",
  "created_at": "2026-04-24T19:41:40.073Z",
  "updated_at": "2026-04-24T19:44:04.865Z",
  "analysis": {
    "vision": { "status": "ok", "medicines": [ … ], "confidence": 0.93 },
    "literacy": { "status": "ok", "items": [ { "name": "…", "explanation": "…" } ], "confidence": 0.0 },
    "food": { "status": "ok", "items": [ { "name": "…", "advice": "…" } ], "confidence": 0.0 },
    "draft_ready_at": "…"
  }
}
```

**If literacy or food fails but vision succeeds (`200`)**:

```json
"literacy": { "status": "failed", "items": [], "confidence": 0.0, "error": "gemini_failed" }
```

Common error values: `gemini_not_configured`, `gemini_failed`, `no_medicines`.

**Errors (with bodies):**

`400` invalid file
```json
{ "detail": "Invalid image type. Allowed: image/jpeg, image/png, image/webp." }
```

`400` empty file
```json
{ "detail": "Empty image file." }
```

`401` auth
```json
{ "detail": "Not authenticated" }
```

`404` user missing
```json
{ "detail": "User not found" }
```

`409` duplicate upload (already confirmed)
```json
{ "detail": "Duplicate confirmed prescription upload detected" }
```

`422` validation
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "language"],
      "msg": "String should have at least 2 characters"
    }
  ]
}
```

---

### `POST /prescriptions/{prescription_id}/confirm`

**Purpose:** Persist medicines + generate **dose schedules** from confirmed (or edited) lines.

**Authentication:** **`Authorization: Bearer <access_token>`**.

**Body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `medicines` | array or omitted / `null` | No | If omitted or `null`, server uses **`analysis.vision.medicines`** from Mongo. Each item may include **`reminder_times_24h`** (`["09:00","21:00"]`); invalid strings → **`422`**. |

**Success — `200 OK`:**

```json
{
  "success": true,
  "prescription_id": "prx_…",
  "status": "confirmed",
  "medicines": [
    {
      "medicine_id": "med_…",
      "name": "…",
      "dosage_pattern": "…",
      "frequency": 2,
      "duration_days": 30,
      "instructions": null,
      "confidence": 0.85,
      "reminder_times_24h": ["09:00", "21:00"]
    }
  ],
  "idempotent": false
}
```

Repeating confirm on an already **`confirmed`** prescription returns **`200`** with **`idempotent: true`** (no duplicate inserts).

**Errors:** `400` (empty / invalid medicines), `401`, `404`, **`409`** if status is not `awaiting_confirmation`.

---

## 5. Dose adherence

### `POST /doses/log`

**Purpose:** Update a single dose log row (`pending` → `taken` | `missed` | `skipped`).

**Authentication:** **`Authorization: Bearer <access_token>`**. Only dose logs whose **`user_id`** equals the JWT’s **`sub`** can be updated.

**Headers:**

| Header | Required | Value |
|--------|----------|--------|
| `Authorization` | Yes | `Bearer <access_token>` |
| `Content-Type` | Yes | `application/json` |

**Body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dose_log_id` | string | Yes | Mongo `_id` of dose log (prefix `dose_…`), min length 8 |
| `status` | string | Yes | One of: `taken`, `missed`, `skipped` |
| `taken_at` | string (ISO 8601 datetime) or `null` | No | When dose was taken (optional) |

**Query:** none.

#### Example request body

```json
{
  "dose_log_id": "dose_abc1234567890",
  "status": "taken",
  "taken_at": "2026-04-24T08:00:00Z"
}
```

#### Example success response — `200 OK`

```json
{
  "success": true,
  "message": "Dose log updated"
}
```

#### Error responses

| Status | `detail` | When |
|--------|----------|------|
| `401` | `Not authenticated` / token errors | Missing or invalid JWT |
| `404` | `Dose log not found` | Unknown id, not `pending`, or log belongs to another user |
| `422` | Validation | Invalid `status` pattern or field types |

### `GET /doses/calendar`

**Purpose:** Return month-level calendar summary for current user (for dashboard month view).

**Authentication:** **`Authorization: Bearer <access_token>`**.

**Query params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `month` | string | Yes | Month in `YYYY-MM` format (e.g. `2026-04`) |
| `tz` | string | No | IANA timezone (e.g. `Asia/Kolkata`), default `UTC` |

#### Example request

```http
GET /doses/calendar?month=2026-04&tz=Asia/Kolkata HTTP/1.1
Authorization: Bearer <access_token>
```

#### Example success response — `200 OK`

```json
{
  "success": true,
  "month": "2026-04",
  "tz": "Asia/Kolkata",
  "days": [
    {
      "date": "2026-04-01",
      "total": 3,
      "taken": 2,
      "missed": 1,
      "skipped": 0,
      "pending": 0
    },
    {
      "date": "2026-04-02",
      "total": 2,
      "taken": 2,
      "missed": 0,
      "skipped": 0,
      "pending": 0
    }
  ]
}
```

#### Error responses

| Status | `detail` (example) | When |
|--------|---------------------|------|
| `401` | `Not authenticated` / `Token expired` / `Invalid or expired token` | Missing or invalid JWT |
| `422` | `month must be in YYYY-MM format` | Invalid `month` query value |
| `422` | `Invalid timezone` | Unsupported/invalid `tz` value |
| `500` | `Internal server error` | Unexpected server failure |

### `GET /doses/day`

**Purpose:** Return all dose rows for one selected date (for day drill-down when user clicks calendar date).

**Authentication:** **`Authorization: Bearer <access_token>`**.

**Query params:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | string | Yes | Date in `YYYY-MM-DD` format |
| `tz` | string | No | IANA timezone (e.g. `Asia/Kolkata`), default `UTC` |

#### Example request

```http
GET /doses/day?date=2026-04-01&tz=Asia/Kolkata HTTP/1.1
Authorization: Bearer <access_token>
```

#### Example success response — `200 OK`

```json
{
  "success": true,
  "date": "2026-04-01",
  "tz": "Asia/Kolkata",
  "items": [
    {
      "dose_log_id": "dose_abc1234567890",
      "medicine_id": "med_9ca7fca0fbf24ad0969f2538d2a4ec66",
      "medicine_name": "Metformin 500mg",
      "scheduled_for": "2026-04-01T08:00:00Z",
      "status": "taken",
      "taken_at": "2026-04-01T08:03:42Z"
    },
    {
      "dose_log_id": "dose_def0987654321",
      "medicine_id": "med_9ca7fca0fbf24ad0969f2538d2a4ec66",
      "medicine_name": "Metformin 500mg",
      "scheduled_for": "2026-04-01T20:00:00Z",
      "status": "missed",
      "taken_at": null
    }
  ]
}
```

#### Error responses

| Status | `detail` (example) | When |
|--------|---------------------|------|
| `401` | `Not authenticated` / `Token expired` / `Invalid or expired token` | Missing or invalid JWT |
| `422` | `date must be in YYYY-MM-DD format` | Invalid `date` query value |
| `422` | `Invalid timezone` | Unsupported/invalid `tz` value |
| `500` | `Internal server error` | Unexpected server failure |

---

## Environment variables (backend)

Frontend typically does **not** read these; they configure the server.

| Variable | Used for |
|----------|-----------|
| `MONGO_URI`, `MONGO_DB_NAME` | Database |
| `SMTP_*`, `EMAIL_FROM` | OTP email delivery |
| `OTP_*` | OTP expiry, cooldown, throttling |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_EXPIRE_MINUTES` | Access JWT after OTP verify |
| `GOOGLE_API_KEY`, `GEMINI_API_BASE_URL`, `GEMINI_VISION_MODEL`, `GEMINI_LITERACY_MODEL`, `GEMINI_FOOD_MODEL`, `GEMINI_TIMEOUT_SECONDS`, `GEMINI_TEMPERATURE`, `GEMINI_MAX_OUTPUT_TOKENS` | Gemini models for vision, literacy, and food |
| `CLOUDINARY_*`, `MAX_PRESCRIPTION_UPLOAD_BYTES` | Image storage |

See `.env.example` in the repository for the full list.

---

## Changelog (API-relevant)

- **2026-04-24:** **Caregivers** — **`/caregivers`** CRUD (multiple per user, JWT), logical **`is_active`** and **`notify_on_missed_dose`**, **soft delete**, unique email per user (non-deleted). **Mongo** collection **`caregivers`** + index on startup.
- **2026-04-25:** Prescription pipeline migrated to Gemini-only models with per-agent model selection: `GEMINI_VISION_MODEL`, `GEMINI_LITERACY_MODEL`, `GEMINI_FOOD_MODEL`.
- **2026-04-24:** Fixed OTP verification when MongoDB returns **naive** `expires_at` / `created_at` datetimes (compare safely against UTC-aware “now”). Auth verify tested end-to-end.
- **2026-04-24:** User documents include optional **`first_name`** / **`last_name`** (default `""`). Added **`PATCH /users/profile`**; verify response includes both fields.
- **2026-04-24:** **JWT access tokens** after **`/auth/otp/verify`**. **`PATCH /users/profile`**, **`POST /prescriptions/upload`**, and **`POST /doses/log`** require **`Authorization: Bearer`**. Prescription upload uses JWT **`sub`** only (no `user_email` form field); dose updates are scoped to token `user_id`.
- **2026-04-24:** **`POST /prescriptions/upload`** — removed **`user_email`** from multipart; user resolved from JWT **`sub`** (`user_id`). Token still carries **`email`** for clients.
- **2026-04-24:** Prescription **draft → confirm** flow: **`POST /prescriptions/upload`** runs AI **synchronously** and returns **`analysis`**; **`POST /prescriptions/{id}/confirm`** commits medicines + doses. Polling **`GET`** removed.

---

## Next steps for your review

1. Confirm **`/auth/otp/request`**, **`/auth/otp/resend`** (after cooldown), and **`/auth/otp/verify`** (copy **`access_token`**) against your deployed base URL with a real inbox.
2. Confirm **`PATCH /users/profile`** with **`Authorization: Bearer`** updates names.
3. **`POST /prescriptions/upload`** (expect long response time while Gemini steps run), then **`POST /prescriptions/{id}/confirm`** when the user accepts the draft.
4. Confirm **`/doses/log`** with **`Authorization: Bearer`** and a `dose_log_id` owned by that user (after step 3).

If you want this document split per milestone (only Auth until signed off), say so and we can trim later sections until you finish testing.
