# Decision Log — Skylark Executive BI Agent

## Key Assumptions

- **Masked/anonymized values are already numeric-clean at the source.** Deal values and
  work-order amounts in the provided data are pre-masked but still numeric (e.g.
  `489360`), so no de-masking logic was needed — only type coercion for the odd string
  or empty cell.
- **"Open" deals define the active pipeline.** Where the assignment asked for pipeline
  health, I treated any deal with a `Deal Status` of `"Open"` (case-insensitive) as part
  of the active pipeline, and everything else (closed-won, closed-lost, etc.) as
  historical.
- **Column titles, not column IDs, are the stable contract.** Since monday.com column
  IDs are auto-generated per-board and unpredictable, the app matches columns by
  fuzzy-matching title substrings (`"value"`, `"amount"`, `"sector"`, `"status"`) rather
  than hardcoding IDs. This makes the app resilient to boards being rebuilt, at the cost
  of being less precise if a founder names a column ambiguously (e.g. a column titled
  "Stage Status" could be mistaken for the deal status column — mitigated by explicitly
  excluding columns with "stage" in the title from the status match).
- **A missing numeric value means "not yet known," not "zero revenue."** Missing values
  are filled with 0 for aggregation purposes but are also counted and surfaced as an
  explicit caveat, so the LLM (and the user) knows the total is a floor, not a fact.

## Trade-offs

| Decision | Why | Cost |
|---|---|---|
| Direct GraphQL calls via `requests` instead of the monday.com SDK or an MCP server | Fewer dependencies, easier to deploy on Streamlit Community Cloud, full control over the exact query shape | More boilerplate than an SDK; no built-in retry/pagination handling |
| Sample 50 rows per board into the LLM context, backed by a pre-computed aggregate summary | Keeps token usage and latency predictable regardless of board size | The LLM can't inspect the full dataset row-by-row for very specific "which exact deal" questions beyond the sample — the aggregate summary covers the common founder-level questions instead |
| Cache monday.com reads for 120 seconds (`st.cache_data`) | Avoids re-querying on every Streamlit rerun (which happens on every keystroke-adjacent widget interaction) | Data can be up to 2 minutes stale; acceptable for a BI dashboard, not for a live ops console |
| Clean only the primary value/amount and status/sector columns per board rather than every column | Time-boxed to the assignment window; these are the columns every sample query in the brief actually touches | Other messy fields (mixed units in "Quantity" columns, inconsistent date formats in `Probable Start/End Date`) are passed through uncleaned and could confuse the LLM on quantity- or scheduling-specific questions |
| System-prompt-only instruction to "ask a clarifying question if broad" rather than code-enforced clarification | Faster to implement, and the LLM handles most ambiguity well in practice | Not deterministic — a genuinely ambiguous query could occasionally get answered with an assumption instead of a question |

## Interpretation of "help prepare data for leadership updates"

I interpreted this as: the agent should be able to produce a structured, numbers-first
snapshot suitable for pasting into a leadership deck or email, on demand, rather than
only answering ad-hoc conversational questions. Concretely, this is implemented as
`summarize_leadership_update()`, which pre-computes: total and open deal counts, total
and open pipeline value, a sector-by-sector value breakdown, and a work-order status
breakdown. This is exposed to the user via the "📊 Leadership Briefing" quick-prompt
button, which asks the agent to turn that structured summary into prose with clear
headers and bullet points — giving a founder a ready-to-share update rather than a raw
number dump.

## What I'd do differently with more time

- **Extend cleaning to every numeric and date column**, not just the primary
  value/amount fields — especially the `Quantity` columns in Work Orders, which mix
  units (e.g. `"5360 HA"` vs. plain integers) and would currently confuse any
  quantity-based query.
- **Add a lightweight intent-classification step before the LLM call** to deterministically
  detect genuinely out-of-scope or ambiguous queries (e.g. a sector name that doesn't
  exist in the data) and short-circuit with a clarifying question, instead of relying
  entirely on the system prompt.
- **Paginate monday.com reads** instead of a single `items_page(limit: 500)` call, so the
  app doesn't silently truncate boards that grow past 500 items.
- **Add basic API failure handling in the UI** (currently `fetch_board_items` swallows
  exceptions and returns an empty DataFrame silently) so a monday.com outage is visibly
  reported to the user instead of looking like "zero deals."
- **Cache the LLM's own leadership-summary output** for a short window, so repeated
  requests for the same briefing don't re-spend tokens unnecessarily.
