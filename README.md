# FinIntel: AI-Powered Financial Document Extraction & Validation Platform

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green)
![Gemini](https://img.shields.io/badge/Gemini-2.5--Flash-orange)

An end-to-end production-ready technical case study platform for ingesting, validating, extracting, mathematically validating, persisting, and visualizing financial documents (Invoices, Balance Sheets, Profit & Loss Statements, and Cash Flow Statements).

---

## 1. Problem Statement

Financial document processing often suffers from two major vulnerabilities when using LLMs alone:
1. **Arithmetic Hallucinations**: Large Language Models are prone to calculation errors and should never be trusted to decide whether complex financial statement math is strictly correct (`PASS`/`FAIL`).
2. **Brittle Pre-Processing**: Systems frequently crash when presented with corrupt files, multi-page PDFs, scanned images, or malformed data.

**FinIntel** solves this by strictly separating the system architecture into distinct layers:
- **Google Gemini 2.5 Flash** performs **multimodal structured extraction** into Pydantic JSON models.
- **Python Deterministic Engine** executes exact `Decimal` arithmetic validation checks across document types and multi-period statements.

---

## 2. Supported Financial Documents & File Formats

### Supported Document Types
1. **Invoice**
2. **Balance Sheet**
3. **Profit & Loss Statement**
4. **Cash Flow Statement**

### Supported File Formats
- **PDF** (Max **3 pages**, native text or scanned)
- **JPG / JPEG**
- **PNG**

---

## 3. High-Level Architecture & Data Flow

```mermaid
flowchart TD
    U[User / Dashboard UI]
    API[FastAPI Backend Web Service]
    V[Multilayer File Validator]
    P[PyMuPDF / Pillow Document Processor]
    AI[Google Gemini 2.5 Flash API]
    X[Structured JSON Normalizer]
    VE[Deterministic Financial Validation Engine]
    DB[(SQLite / Supabase PostgreSQL)]

    U -->|Upload Document| API
    API --> V
    V -->|Validated Stream| P
    P -->|Images & Extracted Text| AI
    AI -->|Structured JSON Output| X
    X -->|Normalized Entities| VE
    VE -->|Validation Checks & Math Status| DB
    X -->|Extracted JSON| DB
    DB -->|Persisted Query Results| API
    API -->|Interactive Dashboard Response| U
```

---

## 4. Tech Stack & Engineering Rationale

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **AI / LLM** | Google Gemini 2.5 Flash | Free/low-cost tier, ultra-fast latency, native multimodal image/document understanding, and native JSON schema output. |
| **Backend Framework** | FastAPI (Python 3.10+) | Asynchronous, automatic OpenAPI/Swagger documentation generation, strict data validation with Pydantic v2. |
| **Document Engine** | PyMuPDF (`fitz`) & Pillow | High-performance C-backed PDF text parsing, page rendering (200 DPI PNGs for scanned OCR), and image verification. |
| **Financial Validation** | Python `Decimal` Engine | Absolute mathematical precision for currency arithmetic, configurable tolerance, and multi-period period isolation. |
| **Database** | SQLAlchemy + SQLite / PostgreSQL | Zero-dependency SQLite for local dev, seamless production migration to Supabase PostgreSQL via single `DATABASE_URL`. |
| **Frontend** | HTML5, CSS3, Vanilla JS | Zero build step complexity, fast performance, served directly from FastAPI single web service. |
| **Deployment** | Render Web Service | Free HTTPS hosting binding to `0.0.0.0:$PORT` for single-service API + Frontend deployment. |

---

## 5. System Layer Breakdown

```
UPLOAD
  ↓
FILE VALIDATION (Existence, size limits, magic bytes, PDF page count ≤ 3, image decodability)
  ↓
DOCUMENT PROCESSING (PyMuPDF text extraction or page rendering to 200 DPI PNG images)
  ↓
AI STRUCTURED EXTRACTION (Gemini 2.5 Flash prompt enforcing zero hallucination & null missing values)
  ↓
NORMALIZATION (Currency symbol stripping, thousand separator handling, (5,000) -> -5000)
  ↓
DETERMINISTIC FINANCIAL VALIDATION (Python Decimal calculations: PASS / FAIL / NOT_APPLICABLE)
  ↓
DATABASE PERSISTENCE (SQLAlchemy storing extraction, validation results & metadata)
  ↓
API RESPONSE & FRONTEND DISPLAY (Interactive dashboard, filterable document list, tabbed result viewer, Raw JSON)
```

---

## 6. Financial Validation Engine Rules

The platform runs document-specific deterministic checks in Python:

### A. Invoice Validation
- **Line Item Math**: `Quantity × Unit Price ≈ Line Total` (for each item).
- **Line Item Sum**: `Sum(Line Totals) ≈ Subtotal`.
- **Tax Relationship**: `Subtotal + Tax ≈ Total`.
- **Amount Due**: `Total - Amount Paid ≈ Amount Due`.

### B. Balance Sheet Validation (Evaluated per period)
- **Fundamental Accounting Equation**: `Capital & Equity + Liabilities ≈ Total Assets`.
- **Asset Breakdown**: `Current Assets + Non-Current Assets ≈ Total Assets`.
- **Liability Breakdown**: `Current Liabilities + Non-Current Liabilities ≈ Total Liabilities`.

### C. Profit & Loss Validation (Evaluated per period)
- **Total Income**: `Primary Income + Other Income ≈ Total Income`.
- **Total Expenditure**: `Operating Expenses + Provisions & Interest ≈ Total Expenditure`.
- **Net Profit**: `Total Income - Total Expenditure ≈ Profit Before Tax / Net Profit`.

### D. Cash Flow Validation (Evaluated per period)
- **Net Increase**: `Operating + Investing + Financing Cash Flows + FX Effect ≈ Net Increase`.
- **Closing Cash**: `Opening Cash + Net Increase + Adjustments ≈ Closing Cash`.
- *Note*: Parentheses e.g., `(20,000)` are automatically converted to negative values `-20000.0`.

---

## 7. Local Setup & Quickstart

### Prerequisites
- Python 3.10 or higher
- Git

### Installation Steps

1. **Clone Repository**:
   ```bash
   git clone https://github.com/your-username/financial-document-intelligence.git
   cd financial-document-intelligence
   ```

2. **Create & Activate Virtual Environment**:
   - **Windows**:
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install Dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy `.env.example` to `.env` inside `backend/`:
   ```bash
   cp backend/.env.example backend/.env
   ```
   Edit `backend/.env` and set your `GEMINI_API_KEY`:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   DATABASE_URL=sqlite:///./financial_docs.db
   MAX_FILE_SIZE_MB=10
   VALIDATION_ABSOLUTE_TOLERANCE=1.0
   VALIDATION_RELATIVE_TOLERANCE=0.01
   ENVIRONMENT=development
   ```

5. **Generate Sample Test Documents**:
   ```bash
   python samples/generate_samples.py
   ```

6. **Run Server Locally**:
   ```bash
   PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

7. **Access Application**:
   - **Web Dashboard**: `http://localhost:8000`
   - **Swagger API Docs**: `http://localhost:8000/docs`
   - **Health Endpoint**: `http://localhost:8000/api/v1/health`

---

## 8. Running Automated Tests

The test suite runs 100% offline without needing a live Gemini API key (all AI calls are mocked using `pytest` fixtures).

Execute tests from the project root:
```bash
PYTHONPATH=backend pytest backend/tests/ -v
```

### Verified Test Coverage:
- File validation (valid PDFs, PNGs, JPGs, corrupt PDFs, empty files, unsupported extensions, PDFs > 3 pages).
- Invoice validation (PASS, FAIL, missing fields, line item math).
- Balance sheet validation (PASS, FAIL, multi-period isolation).
- Profit & Loss validation (PASS, FAIL).
- Cash flow validation (PASS, FAIL, negative parentheses numbers).
- API Integration endpoints (`/health`, `/documents`, `/documents/process`, `/documents/{document_name}`).

---

## 9. Environment Variables Specification

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API key for extraction | `AIzaSy...` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./financial_docs.db` or `postgresql://...` |
| `MAX_FILE_SIZE_MB` | Maximum allowed upload size | `10` |
| `VALIDATION_ABSOLUTE_TOLERANCE` | Max absolute variance for PASS status | `1.0` |
| `VALIDATION_RELATIVE_TOLERANCE` | Max relative variance ratio | `0.01` |
| `ENVIRONMENT` | Application mode | `development` / `production` |
| `PORT` | Web server port (injected by Render) | `8000` |

---

## 10. Deployment Guide

### Deploying to Render & Supabase PostgreSQL

1. **Database Setup (Supabase)**:
   - Create a free PostgreSQL project on Supabase.
   - Copy the database connection string (`postgresql://postgres:[password]@db.[project-id].supabase.co:5432/postgres`).

2. **Render Web Service Deployment**:
   - Connect your GitHub repository to Render.
   - Create a new **Web Service**.
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add Environment Variables in Render Dashboard:
     - `GEMINI_API_KEY`: Your key
     - `DATABASE_URL`: Your Supabase connection string
     - `ENVIRONMENT`: `production`

---

## 11. Known Limitations & Future Improvements

- **Maximum PDF Length**: Limited to 3 pages per specification. Can be extended with asynchronous background task queues (Celery/Redis) for 100+ page documents.
- **Complex Table Structure Alignment**: Extremely dense multi-nested financial tables benefit from specialized fine-tuned OCR layout models.

---

## 12. AI & Tool Usage Declaration

This project was built, tested, and verified using Google Gemini AI agentic tools for internship technical case study demonstration purposes.
