# Skylark Executive BI Agent

A conversational business-intelligence agent that answers founder-level questions about
Skylark Drones' sales pipeline and work-order operations by querying live data directly
from monday.com — no hardcoded CSVs.

## Architecture

```
┌─────────────┐      GraphQL (read-only)      ┌──────────────┐
│  monday.com │ ─────────────────────────────▶│   app.py     │
│  Deals board│                                │  (Streamlit) │
│  WO board   │                                └──────┬───────┘
└─────────────┘                                       │
                                                       │ cleaned DataFrames
                                                       │ + leadership metrics
                                                       ▼
                                              ┌──────────────────┐
                                              │  Gemini (via     │
                                              │  OpenAI-compat   │
                                              │  chat endpoint)  │
                                              └──────────────────┘
                                                       │
                                                       ▼
                                              Conversational answer
                                              rendered in chat UI
```

**Stack**
- **Streamlit** — UI, chat interface, session state, sidebar diagnostics.
- **monday.com GraphQL API** — read-only access to the two boards (Deals, Work Orders).
  Called directly with `requests` rather than the monday SDK/MCP server, to keep the
  deployment footprint (and its dependency surface) as small as possible for a hosted
  demo.
- **pandas** — normalizes column names/types and computes aggregate metrics before
  anything reaches the LLM.
- **Gemini** (`gemini-3.6-flash`) — called through the OpenAI-compatible endpoint so the
  same `openai` SDK can be swapped to a different provider later with minimal changes.
- **`st.cache_data(ttl=120)`** — avoids hammering the monday.com API on every rerun while
  still keeping "live" data reasonably fresh.

## How data flows

1. `fetch_board_items()` pulls every item + column value from a given board ID via a
   single GraphQL query (`items_page`), and maps monday.com's internal column IDs back
   to their human-readable titles.
2. `clean_and_normalize_data()` coerces value/amount columns to numeric, fills missing
   entries with 0, and records a plain-English caveat for every field it had to patch.
3. `summarize_leadership_update()` pre-aggregates deal counts, pipeline value (total vs.
   open), sector breakdown, and work-order status breakdown into a compact JSON blob.
4. That JSON blob — plus a capped sample of raw rows from each board and the caveats
   list — is injected into the system prompt on every turn, so the LLM reasons over
   real, current numbers rather than guessing.
5. The user's question and full chat history are sent to Gemini, and the response is
   streamed back into the Streamlit chat window.

## Setup

### 1. Prerequisites
- Python 3.10+
- A monday.com account with the Deals and Work Orders CSVs imported as two separate
  boards
- A monday.com API token and a Gemini API key

### 2. Import the data into monday.com
1. Create two boards: **Deals** and **Work Orders**.
2. Import `Deal_funnel_Data.xlsx` and `Work_Order_Tracker_Data.xlsx` respectively using
   monday.com's built-in "Import from Excel" tool.
3. Let monday.com auto-detect column types where possible; text/status columns are fine
   as-is since the app treats all column values as text and cleans them in Python.
4. Note each board's numeric ID from its URL
   (`https://<your-account>.monday.com/boards/<BOARD_ID>`).

### 3. Get your API keys
- **monday.com**: Avatar → Admin → API → generate a personal API token (v2, read scope
  is sufficient).
- **Gemini**: Google AI Studio → API Keys.

### 4. Configure environment variables
Create a `.env` file in the project root (this file is git-ignored — never commit it):

```
MONDAY_API_KEY=your_monday_token
GEMINI_API_KEY=your_gemini_key
DEALS_BOARD_ID=your_deals_board_id
WORK_ORDERS_BOARD_ID=your_work_orders_board_id
```

### 5. Install dependencies and run

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 6. Deploying (hosted prototype)
The app is deployed on Streamlit Community Cloud. To redeploy your own copy:
1. Push this repo to GitHub (with `.env` excluded via `.gitignore`).
2. On share.streamlit.io, create a new app pointing at `app.py`.
3. Add the four environment variables above under **Settings → Secrets** in TOML format:
   ```toml
   MONDAY_API_KEY = "..."
   GEMINI_API_KEY = "..."
   DEALS_BOARD_ID = "..."
   WORK_ORDERS_BOARD_ID = "..."
   ```

## Known limitations
See `DECISION_LOG.md` for the full list of trade-offs, but in short: the agent samples
the first 50 rows per board into the LLM context rather than the full dataset, and
numeric cleaning currently targets the primary value/amount column per board rather than
every numeric field.
