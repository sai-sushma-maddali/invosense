# InvoSense

**Autonomous accounts-payable pipeline** — ingest invoices, extract fields with vision AI, run compliance checks, and settle approved payments on testnet.

Built for the **Harness Engineering Hackathon**.

> **Demo video:** uploaded in **Artifacts**.

---

## Problem

Finance teams spend hours on repetitive AP work: downloading invoice attachments, keying data into ERPs, checking tax rates and vendor rules, chasing approvals, and triggering payments. Errors slip through; rejected invoices are hard to trace and fix.

**InvoSense** automates this end-to-end with human override only where it matters.

---

## Who it's for

| User | Benefit |
|------|---------|
| **AP / finance ops** | Invoices from Gmail are processed automatically; flags show *why* something failed with linked tax rules |
| **Controllers** | Compliance runs against vendor master, tax rules, and policy limits before any payment |
| **Managers** | Dashboard for approve / reject; edit extracted values and re-run compliance without re-OCR |

---

## Architecture

InvoSense is **two-tier**: a **FastAPI** backend orchestrates ingest → extract → compliance → decision per invoice; an **Express** dashboard syncs state, handles human review, and settles payments on testnet.

```
                    ┌────────────────────────────────┐
                    │   Invoice attachments          │
                    └───────────────┬────────────────┘
                                    │
                        Composio Gmail poll (30s) 
                                    │
                                    ▼
          ┌─────────────────────────────────────────────────────────┐
          │  Per invoice — autonomous AP agent (FastAPI :8002)      │
          │                                                         │
          │  1. INGEST    save to data/inbox · mark Gmail read      │
          │  2. EXTRACT   Claude vision (TrueFoundry) + Tesseract  │
          │  3. COMPLY    ClickHouse — vendor · tax · totals · dups │
          │  4. DECIDE    auto_approve  OR  rejected + flag reasons │
          │  5. PERSIST   store + JSON artifacts · GET /invoices    │
          │                                                         │
          │  ↻ Human override: PATCH /extraction → COMPLY → DECIDE  │
          │    (merge edits · optional OCR refresh — no new LLM)    │
          └────────────┬──────────────────────────┬─────────────────┘
                       │                          │
     invoice state · pipeline · compliance flags  │  auto_approve · manager approve
                       │                          │
                       ▼                          ▼
       ┌───────────────────────────┐    ┌─────────────────────────────┐
       │  Dashboard (Express :3000)│    │  Settlement + audit trail │
       │  • Invoice table + stats  │    │  • X402 USDC · Base Sepolia │
       │  • Pipeline step tracker  │    │  • cited.md publish       │
       │  • Flags → /tax-rules     │    │  • tx hash on dashboard   │
       │  • Edit & re-run · approve│    │  • ↻ Manual re-run badge  │
       └───────────────────────────┘    └─────────────────────────────┘
```

**Agent roles**

| Step | Agent / service | What it does |
|------|-----------------|--------------|
| **INGEST** | GmailWatcher · FolderWatcher · upload API | Detect new attachments, copy to `data/inbox`, kick off pipeline thread |
| **EXTRACT** | Claude via TrueFoundry + Tesseract | Structured fields (company, GST, amounts) + bounding boxes on image |
| **COMPLY** | ClickHouse Cloud checks | Vendor approval, Malaysia tax-rate lookup, totals validation, duplicate detection |
| **DECIDE** | Policy engine (`approve.py`) | `auto_approve` when clean and within limits; else `rejected` with per-check reasons |
| **PERSIST** | Invoice store + JSON files | `data/extractions/`, `data/compliance/` — polled by Express |
| **Dashboard** | Express + `index.html` | Live sync, human approve/reject, edit & re-run compliance |
| **Settlement** | CDP wallet + viem + cited.md | Pay on testnet after approve; publish audit record |

---

## Tech stack

| Technology | Role |
|------------|------|
| **Composio** | Gmail OAuth and **polling** for unread messages with attachments — no custom IMAP plumbing |
| **FastAPI + Uvicorn** | Backend API, background pipeline, health and invoice endpoints |
| **TrueFoundry Gateway** | Routes vision LLM calls (Claude) for structured invoice extraction |
| **Tesseract + pytesseract** | Word bounding boxes on the receipt image |
| **ClickHouse Cloud** | Reference data: vendors, tax rules, invoice history, policy config |
| **Express + TypeScript** | Frontend server; syncs live data from FastAPI |
| **Coinbase CDP + viem** | X402-style USDC payment on **Base Sepolia** testnet |
| **cited.md** (stub/real) | Publish payment proof for audit trail |

---

## Core features

- **Gmail ingest** — watcher polls unread emails with attachments via Composio; PDF/images enter the pipeline automatically
- **Mark as read** — after attachments are saved and processing starts, the email is marked **read** in Gmail (won’t be picked up again)
- **Vision extraction** — company, GST ID, invoice no, date, amounts + confidence scores
- **Bounding boxes** — field overlays on the invoice image (Tesseract)
- **Compliance** — duplicate detection, totals validation, vendor verification, Malaysia tax-rate lookup
- **Source citation** — every compliance flag links to the **tax rules source** (`/tax-rules`); payment proofs can be published to **cited.md**
- **Human-in-the-loop** — auto-approve only when checks pass; flagged/rejected invoices need review; managers **Approve & Pay** or **Reject**; edit extracted values and **re-run compliance** without re-OCR
- **Edit & re-run** — correct OCR mistakes; **↻ Manual re-run** badge shows on the dashboard after a correction
- **X402 payment** — settle clean invoices on Base Sepolia testnet; transaction log on the dashboard
- **Folder / upload** — alternative ingest paths for demos and testing

---

## Setup

Do these steps **in order**.

### 1. Prerequisites

- Python 3.11+
- Node.js 20+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed (Windows: add path to `.env` as `TESSERACT_CMD`)
- Accounts: Composio, TrueFoundry, ClickHouse Cloud (optional: Coinbase CDP for live testnet pay)

### 2. Backend

```cmd
cd "GIT Code\invosense"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install clickhouse-connect pytesseract
```

Copy and fill environment variables (see keys below). Create `.env` in the project root:

| Variable | Purpose |
|----------|---------|
| `COMPOSIO_API_KEY`, `COMPOSIO_USER_ID`, `COMPOSIO_GMAIL_AUTH_CONFIG_ID` | Gmail polling |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` | Google OAuth (via Composio) |
| `TFY_GATEWAY_URL`, `TFY_API_KEY`, `TFY_MODEL` | Vision extraction |
| `TESSERACT_CMD`, `EXTRACT_WITH_BOXES=true` | Bounding boxes |
| `CLICKHOUSE_*` | Compliance database |

Seed ClickHouse (first run):

```cmd
python -m compliance_code.seed
```

### Connect Gmail to Composio

**A. Google Cloud OAuth client** (one-time)

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Gmail API**
3. Create **OAuth 2.0 Client ID** (Desktop or Web)
4. Add these **Authorized redirect URIs**:
   ```
   https://backend.composio.dev/api/v3.1/toolkits/auth/callback
   https://backend.composio.dev/api/v3/toolkits/auth/callback
   https://backend.composio.dev/api/v1/auth-apps/add
   ```
5. Copy **Client ID** and **Client Secret** into `.env` as `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`
6. Add your Gmail account as a **test user** (OAuth consent screen)

**B. Composio + InvoSense**

1. Get `COMPOSIO_API_KEY` from [Composio Settings](https://app.composio.dev/settings)
2. Set in `.env`: `COMPOSIO_API_KEY`, `COMPOSIO_USER_ID=default`
3. Run the connect helper:

```cmd
python connect_gmail.py --status
python connect_gmail.py --recreate-auth-config --wait
```

4. Sign in with the Gmail inbox you want to watch when the browser opens
5. Confirm: `python connect_gmail.py --status` → `connected: true`
6. **Restart the backend** so the watcher picks up the new connection

Alternatively, while the API is running: `GET http://127.0.0.1:8002/connect/gmail` returns the OAuth URL.

Start the API (**port 8002**):

```cmd
python -m uvicorn main:app --host 127.0.0.1 --port 8002
```

Verify: `http://127.0.0.1:8002/health` → `gmail_connected: true`

### 3. Frontend

```cmd
cd frontend
npm install
```

Create `frontend/.env`:

```env
PORT=3000
BACKEND_URL=http://localhost:8002
```

Optional (testnet payments): `CDP_API_KEY`, `WALLET_PRIVATE_KEY` — see `frontend/.env.example`.

```cmd
npm run dev
```

Open **http://localhost:3000**

### 4. Try it

1. Send an invoice image/PDF to the connected Gmail inbox (unread + attachment) — or use `POST /upload`
2. Email is marked **read** after ingest; watch the dashboard update every 5s
3. Open **View Invoice** for OCR + bounding boxes
4. On rejection: **View Reason** (with tax-rule source link) → **Edit & Re-run**
5. For flagged items: **Approve & Pay** or **Reject** from the review panel

---

## Project layout

```
invosense/
├── main.py              # FastAPI entrypoint
├── ingest.py            # Save + pipeline orchestration
├── extract_runner.py    # Vision extraction bridge
├── compliance_code/     # ClickHouse checks
├── extraction_code/     # LLM extraction module
├── frontend/            # Dashboard (port 3000)
├── data/                # inbox, extractions, compliance JSON
├── connect_gmail.py     # Composio OAuth helper
└── .env                 # Secrets (do not commit)
```

---

## API (quick reference)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Backend + Gmail status |
| `GET` | `/invoices` | All invoice records |
| `PATCH` | `/invoices/{id}/extraction` | Edit fields + re-run compliance |
| `POST` | `/invoices/{id}/retry` | Retry compliance or refresh boxes |
| `POST` | `/upload` | Upload invoice file |
| `GET` | `/compliance/tax-rules` | Tax rules source document |

---

## Notes

- Payments use **Base Sepolia testnet** and a mock MYR→USDC rate — not production finance.
- After editing `.env` or connecting Gmail, **restart the backend**.
- If port 3000 is busy, stop the old frontend process before `npm run dev`.

---

## License

Hackathon submission — Harness Engineering Hackathon 2026.
