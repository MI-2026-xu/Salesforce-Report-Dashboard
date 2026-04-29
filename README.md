# Salesforce AI Report Dashboard

> **Ask questions in plain English. Get real Salesforce data back — as tables, charts, and summaries — instantly.**

A production-grade AI agent that sits on top of your Salesforce org and lets any team member — sales, ops, finance, leadership — query CRM data without writing a single line of SOQL. Powered by Claude AI (Anthropic), FastAPI, and Next.js.

---

## What This Is

Most teams have data locked inside Salesforce that only admins or RevOps analysts can extract. Filters, reports, and dashboards require setup time. Ad-hoc questions ("how many open leads came from India last quarter?") either wait in a queue or go unanswered.

This project removes that bottleneck entirely.

You type a question. The AI agent interprets your intent, fetches the correct Salesforce schema, generates a safe SOQL query, runs it, and returns the results — structured, summarized, and visualized — in under 5 seconds.

No SOQL knowledge required. No report builder. No admin request.

---

## Business Impact

| Problem Today | With This Agent |
|---|---|
| Analyst spends 2–4 hrs building a custom report | Any team member gets the answer in < 10 seconds |
| SOQL errors return blank results or crash | Agent validates the query, retries automatically, explains failures |
| Follow-up questions require a new report | Conversational memory — "now filter by last 30 days" just works |
| Leadership asks for a chart, gets a spreadsheet | Agent auto-selects bar, pie, or table based on data shape |
| Non-technical users are blocked from CRM insights | Natural language interface accessible to everyone |
| Custom reports take IT resources to maintain | Zero maintenance — agent reads live schema at query time |

### Real-World Use Cases

- **Sales leadership** — "Show me open opportunities above $50K closing this quarter"
- **Marketing ops** — "How many leads came from each source in the last 90 days, grouped by status?"
- **Finance** — "What is the total closed-won ARR for enterprise accounts this fiscal year?"
- **HR / Recruiting** — "List all contacts added in the last 30 days from the technology sector"
- **Customer success** — "Which accounts have had no activity in the last 60 days?"

---

## How the Agent Works

The system is built in four layers, each with a clear responsibility:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1 — User (Browser)                           │
│  Types a question in plain English                  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP POST
┌──────────────────────▼──────────────────────────────┐
│  Layer 2 — Next.js Frontend                         │
│  Chat UI · ResultTable · ResultChart · Debug panel  │
└──────────────────────┬──────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────┐
│  Layer 3 — FastAPI + Claude Agent (Python)          │
│  Intent parsing → Schema fetch → SOQL generation    │
│  → Validation → Retry → Result synthesis            │
└──────────────────────┬──────────────────────────────┘
                       │ simple_salesforce
┌──────────────────────▼──────────────────────────────┐
│  Layer 4 — Salesforce Connector                     │
│  get_schema() · run_soql() · get_available_objects()│
│  In-memory caching · Safe error handling            │
└─────────────────────────────────────────────────────┘
```

### Agent Decision Loop (Layer 3 Detail)

```
User query
    │
    ▼
Claude receives query + system prompt (safety rules)
    │
    ├─► Tool call: get_available_objects()
    │       └─► Returns list of all queryable SF objects
    │
    ├─► Tool call: get_schema(object_name)
    │       └─► Returns real field names + types (cached 1hr)
    │
    ├─► Claude generates SOQL using only real fields
    │
    ├─► Python validator checks:
    │       • All fields exist in schema
    │       • No DELETE / UPDATE / INSERT
    │       • LIMIT clause present
    │       └─► If invalid → send error back to Claude → retry (max 2x)
    │
    ├─► Tool call: run_soql(query)
    │       └─► Returns paginated records from Salesforce
    │
    └─► Claude synthesizes response:
            • One-sentence summary
            • chartType recommendation (table / bar / pie)
            • Optional business insight
```

### Why Claude (Anthropic) as the Agent Brain

Claude is used for three distinct reasoning tasks in this pipeline:

1. **Intent classification** — understanding what SF object and fields the user is asking about, even with vague or ambiguous phrasing
2. **Schema-aware SOQL generation** — generating syntactically correct queries constrained to the actual fields that exist in the org
3. **Result synthesis** — reading raw SF records and producing a business-readable summary with chart type selection

Claude's tool use capability is what makes the agentic loop possible — it decides *which tools to call, in what order, with what arguments*, autonomously, without hardcoded routing logic.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| AI Agent | Anthropic Claude (`claude-sonnet-4-6`) | Intent parsing, SOQL generation, result synthesis |
| Backend | Python 3.11 + FastAPI | REST API server, agent orchestration |
| SF Connector | `simple_salesforce` | Salesforce REST API client |
| Frontend | Next.js 14 + TypeScript | Chat UI, routing, API proxy |
| Styling | Tailwind CSS | Utility-first responsive styling |
| Charts | Recharts | Bar, pie, and table visualizations |
| Backend Deploy | Railway | Python/FastAPI hosting |
| Frontend Deploy | Vercel | Next.js hosting, CDN |
| Auth / Secrets | `.env` + platform env vars | SF credentials, Anthropic API key |

---

## Project Structure

```
salesforce-report-dashboard/
│
├── backend/
│   ├── sf_connector.py       # Layer 4 — Salesforce connection, schema, SOQL runner
│   ├── tools.py              # Claude tool definitions (JSON schemas)
│   ├── agent.py              # Layer 3 — Claude agent loop, intent parsing, validator
│   ├── main.py               # FastAPI server — routes, CORS, session memory
│   ├── test_connector.py     # Integration tests for Layer 4
│   ├── seed_data.py          # Script to load demo data into SF Dev Org
│   ├── requirements.txt      # Python dependencies
│   ├── Dockerfile            # Container config for Railway
│   └── railway.toml          # Railway deployment config
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Main chat page
│   │   └── api/query/
│   │       └── route.ts      # Next.js API proxy to Python backend
│   ├── components/
│   │   ├── ChatMessage.tsx   # User / agent message bubbles
│   │   ├── ResultTable.tsx   # Sortable data table with CSV export
│   │   └── ResultChart.tsx   # Bar / pie chart via Recharts
│   ├── tailwind.config.ts
│   └── package.json
│
├── .env.example              # Environment variable template
└── README.md
```

---

## Prerequisites

Before you begin, you need:

- **Python 3.11+** — [python.org](https://python.org)
- **Node.js 18+** — [nodejs.org](https://nodejs.org)
- **Git** — [git-scm.com](https://git-scm.com)
- **Salesforce Developer Org** — Free at [developer.salesforce.com](https://developer.salesforce.com/signup)
- **Anthropic API Key** — [console.anthropic.com](https://console.anthropic.com)
- **VS Code** (recommended)

---

## Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Salesforce credentials (from your Dev Org → Setup → My Personal Information → Reset Security Token)
SF_USERNAME=your_sf_username@example.com
SF_PASSWORD=your_sf_password
SF_SECURITY_TOKEN=your_sf_security_token
SF_DOMAIN=login                          # use 'test' for sandbox orgs

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# App config
CORS_ORIGIN=http://localhost:3000        # set to your Vercel URL in production
```

Create a `.env.local` file in the `frontend/` directory:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000   # set to your Railway URL in production
```

> **Security note:** `.env` files are in `.gitignore`. Never commit credentials. Use Railway and Vercel's environment variable dashboards for production secrets.

---

## Local Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/salesforce-report-dashboard.git
cd salesforce-report-dashboard
```

### 2. Backend setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials.

Start the FastAPI server:

```bash
uvicorn main:app --reload --port 8000
```

Verify it's running:

```
GET http://localhost:8000/api/health  →  { "status": "ok" }
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — you should see the chat interface.

### 4. Test the connection

In the browser, type:

```
Show me the 10 most recently created leads
```

You should see a table with real Salesforce records.

---

## Running Tests

### Backend integration tests (Layer 4)

```bash
cd backend
python -m pytest test_connector.py -v
```

Runs 10 test cases:
- Schema fetch for Lead, Opportunity, Account
- 5 SOQL queries of increasing complexity
- 1 intentional error case (invalid field)
- 1 cache hit verification

All 10 must pass before moving to agent development.

---

## API Reference

### `POST /api/query`

Main agent endpoint. Accepts a natural language query, returns structured results.

**Request body:**
```json
{
  "query": "Show me open leads from India created this month",
  "session_id": "optional-uuid-for-conversation-memory"
}
```

**Response:**
```json
{
  "summary": "Found 14 open leads from India created in April 2026.",
  "rows": [
    { "Name": "Ravi Kumar", "Status": "Open", "LeadSource": "Web", "Country": "India" }
  ],
  "soql": "SELECT Name, Status, LeadSource, Country FROM Lead WHERE Country = 'India' AND Status = 'Open' AND CreatedDate = THIS_MONTH LIMIT 200",
  "chartType": "table",
  "rowCount": 14,
  "insight": "Web is the top lead source at 43%."
}
```

### `GET /api/health`

Returns server status and Salesforce connection state.

### `GET /api/objects`

Returns all queryable Salesforce object names available in the connected org.

---

## Deployment

### Backend → Railway

1. Create a free account at [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Railway auto-detects the `Dockerfile` in `backend/`
4. Add all environment variables in the Railway dashboard
5. Deploy — your backend URL will be `https://your-app.railway.app`

### Frontend → Vercel

1. Create a free account at [vercel.com](https://vercel.com)
2. Import your GitHub repository
3. Set root directory to `frontend/`
4. Add environment variable: `NEXT_PUBLIC_API_URL=https://your-app.railway.app`
5. Deploy — your app URL will be `https://your-app.vercel.app`

---

## Safety & Guardrails

The agent enforces strict safety rules at both the prompt and code level:

| Rule | Where Enforced |
|---|---|
| Read-only — no INSERT, UPDATE, DELETE | System prompt + Python validator |
| All field names validated against live schema | Python validator before every query |
| LIMIT clause always required (max 200 rows) | System prompt + Python validator |
| Invalid queries returned to Claude for self-correction | Retry loop (max 2 attempts) |
| SF credentials never sent to Claude | Backend only — Claude sees schema, not credentials |
| Session history scoped to `session_id` | In-memory — cleared on server restart |

---

## Contributing

This is a focused 30-day build. Keep contributions scoped to the sprint goals.

1. Branch from `main` — name branches `sprint-N/description`
2. Every PR must include a passing test for the Layer it touches
3. No new dependencies without a clear reason documented in the PR
4. Commit daily — no commit = behind

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built by Abhay · Powered by [Claude AI](https://anthropic.com) · Salesforce connector via [simple-salesforce](https://github.com/simple-salesforce/simple-salesforce)*
