# BharatSetu — AI-Powered Integrated Bid Compliance Verification Platform

**Smart India Hackathon 2026 (SIH 2026)**  
**Problem Statement ID:** 26100  
**Organization:** Ministry of Petroleum & Natural Gas (MoPNG)  
**Department:** Chennai Petroleum Corporation Limited (CPCL)  
**Category:** Software  
**Theme:** Smart Automation  

---

## Executive Overview

**BharatSetu** is an AI-assisted bid compliance verification platform for GeM procurement. It processes bidder documents, extracts relevant information, evaluates tender-specific requirements, performs simulated external verification and cross-document checks, calculates compliance and risk scores, generates an explainable summary, and keeps the final procurement decision with an authorized officer.

> [!IMPORTANT]
> **Simulated APIs**: Government verification services are simulated for the SIH prototype and would require authorized G2G/API access for production deployment.

## Demo and business-rule boundaries

- Live tender discovery uses the centralized minimum estimated tender value of **₹1,00,000 and above**.
- Tender and bid amounts remain numeric in the API/database; the frontend formats them using Indian Rupee notation.
- Seeded records and uploaded certificates are synthetic demo data and are not real government records.
- Government integrations run in explicit MOCK/DEMO mode.
- AI assists document verification and explanation; an authorized procurement officer makes the final decision.
- Document integrity is preserved with SHA-256 hashing and the audit trail; no blockchain service is required by the current demo.

---

## Key Features

1. **Integrated Multi-Document Processing Pipeline**:
   - SHA-256 file hashing for instant duplicate document detection.
   - PyMuPDF / pypdf text extraction with Tesseract OCR fallback for scanned certificates.
   - Automated document classification across 30+ compliance categories (GST, PAN, Udyam, EPFO, ESIC, MCA21, Financial Statements, Work Experience, Debarment Declarations, EMD, Local Content, etc.) with confidence scoring and manual officer overrides.

2. **Tender Engine & Requirements Parser**:
   - Allows procurement officers to define tender-specific eligibility rules (Minimum Annual Turnover, Minimum Years Experience, MSME/Startup Exemptions, Local Content % Undertakings, Mandatory vs Optional certificates).

3. **Fuzzy Cross-Document Intelligence**:
   - Cross-checks entity legal names, registered addresses, GSTIN, PAN, CIN, and financial figures across uploaded certificates using token distance fuzzy matching (`RapidFuzz`).
   - Flagging address discrepancies (e.g. Pune GST address vs Nagpur Udyam address) and name variations.

4. **Pluggable Government Verification Architecture**:
   - Pluggable `VerificationProvider` interface supporting `MockGSTProvider`, `MockUdyamProvider`, `MockPANProvider`, `MockEPFOProvider`, `MockESICProvider`, `MockMCAProvider`, `MockStartupProvider`, `MockNSICProvider`, `MockDigiLockerProvider`, and `MockDebarmentProvider`.
   - Explicitly displays `"SIMULATED GOVERNMENT VERIFICATION"` in local demo mode.

5. **Deterministic Risk & Compliance Engine**:
   - Risk Score (0–100: LOW, MEDIUM, HIGH) calculated deterministically from weighted failure signals (missing mandatory docs, address mismatch, debarment matches, expired certificates).
   - Independent Compliance Score % calculation.

6. **Explainable AI & MOCK AI Chatbot**:
   - Grounded summary engine synthesizing verified backend facts without hallucinating document details.
   - Dedicated Bidder-facing `[MOCK AI]` Support Chatbot restricted by strict vendor isolation and Role-Based Access Control (RBAC).

7. **Exact-Match Suggested Tenders Engine**:
   - Analyzes fully verified compliance evidence (`verified=True` and `document_id IS NOT NULL`) to recommend new procurement opportunities to bidders, filtering out processing/failed documents.

8. **Human-in-the-Loop & Immutable Audit Ledger**:
   - Officers retain full authority to Approve, Reject (with mandatory reason), or Flag for Escalation.
   - Every system event is recorded in an immutable audit ledger (`AuditEvent`).
   - Bidder roles are explicitly isolated from accessing administrative UI controls and backend review endpoints.

9. **PDF Compliance Verification Reports**:
   - Automated ReportLab PDF generator exporting official bid compliance verification reports.
   - Explicitly watermarked with a MOCK/DEMO disclaimer to ensure transparency.

---

## Tech Stack

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, Axios, React Router
- **Backend**: Python 3.11 / 3.14, FastAPI, SQLAlchemy 2 ORM, Pydantic V2
- **OCR & ML**: PyMuPDF, pypdf, Tesseract OCR, RapidFuzz
- **Database**: SQLite (local development) / PostgreSQL (production architecture)
- **Deployment**: Docker, Docker Compose, Nginx

---

## Quick Start & Running Locally

### 1. Backend Setup

```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The FastAPI backend uses local disk storage by default. `STORAGE_BACKEND=local` and `UPLOAD_DIR` control where documents are saved.

- **Swagger API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 2. Frontend Setup

In a separate terminal window:

```bash
cd Frontend
npm install
cp .env.example .env
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Running Unit & End-to-End Tests

```bash
python -m pytest backend/tests
```

All 5 backend test suites cover:
- Fuzzy entity name & address matching
- Document classification confidence
- Deterministic risk scoring
- End-to-end user story compliance acceptance flow

---

## Docker Deployment

To build and run the entire full-stack application with Docker Compose:

```bash
docker-compose up --build
```

- **Frontend Application**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:8000](http://localhost:8000)

## Production Deployment

The frontend is deployed as a Vite SPA on Vercel. Set Vercel's project root to the
repository root and configure `VITE_API_BASE_URL` to the Render API origin ending
in `/api` (for example, `https://bharatsetu-api.onrender.com/api`). `vercel.json`
builds the frontend and rewrites SPA routes to `index.html`; it does not run an API.

Deploy the FastAPI service and managed PostgreSQL database from `render.yaml`.
Render runs Alembic migrations before starting Uvicorn. Configure `CORS_ORIGINS`
with the exact Vercel production origin (and any preview origins that are needed).
Set `ENVIRONMENT=production`, a generated `JWT_SECRET_KEY`, the Render
`DATABASE_URL`, and `ENABLE_DEMO_SEED=false`. SQLite is for local development only.
Production requires `STORAGE_BACKEND=s3` and an S3-compatible bucket (Cloudflare R2,
Supabase Storage's S3 endpoint, or another compatible service). Set `S3_ENDPOINT_URL`,
`S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, and `S3_REGION` in the
Render service environment. Keep credentials in deployment settings, never in source
control. New uploads are stored under opaque object keys; the API authorizes document
views before returning a local file or a one-hour presigned object URL. Render runs
`python scripts/migrate_documents_to_s3.py` before Alembic on startup.
The utility checks each legacy source hash, copies the object, and verifies the
stored bytes before migration 0002 removes the old path column. Missing files or
integrity mismatches stop the transfer so they can be resolved before deployment.
For compliance processing, Render also requires `LLM_PROVIDER=gemini` and
`GEMINI_API_KEY`. `GEMINI_MODEL` defaults to `gemini-2.5-flash` and
`GEMINI_TIMEOUT_SECONDS` bounds each request. Gemini receives stored document bytes
directly, returns schema-validated extraction and requirement findings, and does not
require Tesseract in production. Use `LLM_PROVIDER=mock` locally and in CI to use
deterministic extraction and scoring without Gemini API calls. Provider failures are
persisted as `PROCESSING_FAILED` with a retry action; an authorized officer still
makes the final procurement decision.
Government providers remain simulated and the boundary remains **Officer Decides.
AI Verifies.**

Authentication tokens expire after 30 minutes by default. `ACCESS_TOKEN_EXPIRE_MINUTES`
can be set from 1 to 60 minutes. Login and registration are limited to 10 failed
attempts per client IP per minute and return HTTP 429 while the limit is active.
The limiter is process-local; deployments that scale across multiple backend
instances should enforce the same limit at a shared gateway or distributed store.
Officer/admin routes enforce role dependencies, and bidder bid, document, report,
and vendor reads are scoped to the authenticated vendor. Expired frontend sessions
clear the saved token and return the user to sign-in with a session-expired notice.

GitHub Actions runs frontend typecheck/build and backend Alembic/pytest checks for
pushes and pull requests targeting `main`.

---

## Demo Credentials & Pre-Seeded Bidders

- **Procurement Officer**: `officer@bharatsetu.gov.in` / `officer123`
- **Admin**: `admin@bharatsetu.gov.in` / `admin123`
- **Bidder**: `bidder@bharatsetu.gov.in` / `bidder123`

When `ENABLE_DEMO_SEED=true`, local startup seeds demo identities and sample
procurement data. Production deployment sets this flag to `false`; create real
accounts through the registration flow and never rely on demo credentials in
production. Demo passwords are public prototype credentials.

### Pre-Seeded Demonstration Cases:
1. **Shree Lakshmi Industries Pvt Ltd** (HIGH RISK, Score 87): GST address mismatch (Pune vs Nagpur) & EPFO establishment issue.
2. **Bharat Tech Solutions LLP** (LOW RISK, Score 12): 100% verified documents, clean history.
3. **Green Earth Agro Supplies Co.** (MEDIUM RISK): EPFO inactive since June 2026.
4. **National Steel Fabricators Unit** (HIGH RISK): PAN name mismatch.
5. **MediCare Instruments Ltd** (LOW RISK, APPROVED): CDSCO verified.
6. **Vidya Educational Supplies Co.** (HIGH/MEDIUM RISK): GST cancellation flag.
