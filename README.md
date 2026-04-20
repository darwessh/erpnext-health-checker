# ERPNext Health Checker

A tool that connects to any ERPNext instance via its REST API, runs a 22-check audit covering accounting configuration and GL integrity, and produces a scored PDF health report.

A browser-based UI is served at `/` — no REST client needed.

---

## Features

| Category | Checks |
|---|---|
| Chart of Accounts | Leaf accounts without parent group |
| Accounting | Missing cost centers, tax templates, AR/AP accounts |
| Parties | Customers & suppliers missing payment terms |
| Items | Sales/purchase items missing income/expense accounts |
| Configuration | Fiscal year, default currency |
| Transactions | Draft invoices, duplicate payments, unallocated payments, advances not adjusted, payments on cancelled invoices |
| GL Integrity | AR/AP/Stock control-account reconciliation, direct journal entries to control accounts, P&L lines missing cost center |
| Stock Integrity | Negative stock |

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/darwessh/erpnext-health-checker.git
cd erpnext-health-checker
pip install -r requirements.txt
```

### 2. Configure (optional)

```bash
cp .env.example .env
# Edit .env if you need CORS support for cross-origin API access
```

### 3. Run

```bash
# Development
python app.py

# Production (gunicorn)
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app
```

Open **http://localhost:5000** in your browser, enter your ERPNext credentials, and click **Run Audit** to download the PDF report.

---

## Docker

```bash
docker build -t erpnext-health-checker .
docker run -p 5000:5000 erpnext-health-checker
```

Pass environment variables with `-e`:

```bash
docker run -p 5000:5000 \
  -e CORS_ORIGINS=https://app.example.com \
  erpnext-health-checker
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | *(empty)* | Comma-separated list of origins allowed to call `/audit` cross-origin. Leave empty to disable CORS. |
| `FLASK_ENV` | `production` | Set to `development` for debug mode and auto-reload. |

---

## API

The `/audit` endpoint can also be called directly from any HTTP client.

**Request**

```
POST /audit
Content-Type: application/json

{
  "base_url":   "https://your-erpnext.example.com",
  "api_key":    "<api-key>",
  "api_secret": "<api-secret>"
}
```

**Success response** — `200 application/pdf` — binary PDF body (also sent as a download attachment).

**Error responses**

| Status | Meaning |
|---|---|
| 400 | Missing or invalid fields / malformed JSON |
| 401 | ERPNext authentication failed |
| 500 | Unexpected server error |

---

## Running tests

```bash
pytest tests/ -v
```

The suite (74 tests) uses `unittest.mock` — no live ERPNext instance is required.

---

## Project structure

```
app.py           Flask application and /audit route
checks.py        22 configuration-level checks
gl_checks.py     GL integrity and reconciliation checks
report.py        ReportLab PDF generation
handler.py       AWS Lambda entry-point (alternate deployment)
tests/           pytest test suite
templates/       Jinja2 HTML template (index.html)
static/          CSS and JavaScript for the browser UI
Procfile         Gunicorn process declaration (Heroku / Render)
Dockerfile       Container build
.env.example     Environment variable documentation
```

