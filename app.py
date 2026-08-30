import os
import json
import requests
import pandas as pd
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEALS_BOARD_ID = os.getenv("DEALS_BOARD_ID", "5030965336")
WORK_ORDERS_BOARD_ID = os.getenv("WORK_ORDERS_BOARD_ID", "5030965393")
MONDAY_API_URL = "https://api.monday.com/v2"

st.set_page_config(page_title="Skylark Executive BI", page_icon="🦅", layout="wide")

# --- Custom CSS for Professional UI ---
st.markdown("""
    <style>
    /* Clean up the default Streamlit UI */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Style the quick prompt buttons */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        border: 1px solid #4B4B4B;
        background-color: transparent;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        border-color: #00E676;
        color: #00E676;
        box-shadow: 0 4px 12px rgba(0,230,118,0.1);
    }
    
    /* Style the metric cards */
    div[data-testid="metric-container"] {
        background-color: #1E1E1E;
        border-radius: 8px;
        padding: 15px;
        border-left: 4px solid #00E676;
    }
    </style>
""", unsafe_allow_html=True)

# --- Data Fetching & Cleaning ---
def fetch_board_items(board_id: str, limit: int = 500) -> pd.DataFrame:
    if not MONDAY_API_KEY:
        return pd.DataFrame()
    query = """
    query ($boardId: [ID!], $limit: Int!) {
      boards (ids: $boardId) {
        columns { id title }
        items_page (limit: $limit) { items { name column_values { id text } } }
      }
    }
    """
    headers = {"Authorization": MONDAY_API_KEY, "API-Version": "2024-01"}
    variables = {"boardId": [str(board_id)], "limit": limit}

    try:
        response = requests.post(MONDAY_API_URL, headers=headers, json={"query": query, "variables": variables}, timeout=20)
        data = response.json()
        if "errors" in data or "data" not in data or not data["data"]["boards"]:
            return pd.DataFrame()

        board = data["data"]["boards"][0]
        col_map = {col["id"]: col["title"] for col in board["columns"]}
        
        records = []
        for item in board["items_page"]["items"]:
            row = {"Item Name": item["name"]}
            for cv in item["column_values"]:
                row[col_map.get(cv["id"], cv["id"])] = cv["text"]
            records.append(row)
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame()

def clean_and_normalize_data(df_deals: pd.DataFrame, df_wo: pd.DataFrame):
    caveats = []
    if not df_deals.empty:
        val_col = next((c for c in df_deals.columns if "value" in c.lower() or "amount" in c.lower()), None)
        if val_col:
            missing_val = df_deals[val_col].isna().sum() + (df_deals[val_col] == "").sum()
            df_deals[val_col] = pd.to_numeric(df_deals[val_col].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
            if missing_val > 0:
                caveats.append(f"Deals Board: {missing_val} entries have missing deal values (treated as 0).")

    if not df_wo.empty:
        amt_col = next((c for c in df_wo.columns if "amount" in c.lower()), None)
        if amt_col:
            missing_amt = df_wo[amt_col].isna().sum() + (df_wo[amt_col] == "").sum()
            df_wo[amt_col] = pd.to_numeric(df_wo[amt_col].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
            if missing_amt > 0:
                caveats.append(f"Work Orders: {missing_amt} records missing unmasked revenue values.")

    return df_deals, df_wo, caveats

@st.cache_data(ttl=120)
def get_live_data():
    df_deals = fetch_board_items(DEALS_BOARD_ID)
    df_wo = fetch_board_items(WORK_ORDERS_BOARD_ID)
    return clean_and_normalize_data(df_deals, df_wo)

def summarize_leadership_update(df_deals: pd.DataFrame, df_wo: pd.DataFrame) -> str:
    total_deals = len(df_deals)
    val_col = next((c for c in df_deals.columns if "value" in c.lower()), None)
    sector_col = next((c for c in df_deals.columns if "sector" in c.lower()), None)
    status_col = next((c for c in df_deals.columns if "status" in c.lower() and "stage" not in c.lower()), None)

    total_pipeline_val = float(df_deals[val_col].sum()) if (val_col and not df_deals.empty) else 0.0
    open_deals = df_deals[df_deals[status_col].astype(str).str.lower() == "open"] if (status_col and not df_deals.empty) else df_deals
    open_pipeline_val = float(open_deals[val_col].sum()) if (val_col and not open_deals.empty) else 0.0

    sector_breakdown = df_deals.groupby(sector_col)[val_col].sum().to_dict() if sector_col and val_col and not df_deals.empty else {}
    wo_status_col = next((c for c in df_wo.columns if "execution status" in c.lower() or "status" in c.lower()), None)
    wo_status_breakdown = df_wo[wo_status_col].value_counts().to_dict() if wo_status_col and not df_wo.empty else {}

    return json.dumps({
        "total_deals_count": total_deals,
        "open_deals_count": len(open_deals),
        "total_pipeline_value_inr": total_pipeline_val,
        "open_pipeline_value_inr": open_pipeline_val,
        "sector_pipeline_value_inr": sector_breakdown,
        "work_orders_total": len(df_wo),
        "work_orders_by_execution_status": wo_status_breakdown
    }, default=str)

# --- UI Layout ---
st.title("🦅 Skylark Drones — Executive BI Agent")
st.divider()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2040/2040504.png", width=60)
    st.header("Live Connections")
    
    with st.spinner("Syncing monday.com..."):
        df_deals, df_wo, caveats = get_live_data()
    
    col1, col2 = st.columns(2)
    col1.metric("Live Deals", len(df_deals))
    col2.metric("Work Orders", len(df_wo))
    
    st.divider()
    if caveats:
        st.subheader("⚠️ Data Caveats")
        for c in caveats:
            st.warning(c, icon="⚠️")
    
    st.divider()
    if st.button("🔄 Force Data Refresh"):
        st.cache_data.clear()
        st.rerun()

# --- Chat Interface ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Welcome to the Skylark Intelligence layer. How can I assist you with the pipeline or work orders today?"}
    ]

# Display history with custom avatars
for msg in st.session_state.messages:
    avatar = "🦅" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# --- Prompt Handling ---
# 1. Capture text input first
prompt = st.chat_input("Ask a business intelligence question...")

# 2. Render buttons only if chat is empty, and let them override the prompt if clicked
if len(st.session_state.messages) == 1:
    st.markdown("#### Suggested Queries")
    p_col1, p_col2, p_col3 = st.columns(3)
    if p_col1.button("⚡ Energy & Mining Pipeline"):
        prompt = "How is our sales pipeline looking for Mining and Powerline sectors this quarter?"
    if p_col2.button("🚧 Work Order Bottlenecks"):
        prompt = "What is the breakdown of our Work Order execution statuses, and are there stalled projects?"
    if p_col3.button("📊 Leadership Briefing"):
        prompt = "Prepare a structured leadership update summarizing our pipeline health and operations status."

# 3. Process the prompt (whether typed or clicked)
if prompt:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Generate and stream assistant response
    with st.chat_message("assistant", avatar="🦅"):
        if not GEMINI_API_KEY:
            st.error("Please configure your GEMINI_API_KEY in `.env`.")
        else:
            client = OpenAI(
                api_key=GEMINI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            
            leadership_metrics = summarize_leadership_update(df_deals, df_wo)
            deals_sample = df_deals.head(50).to_dict(orient="records") if not df_deals.empty else []
            wo_sample = df_wo.head(50).to_dict(orient="records") if not df_wo.empty else []

            system_prompt = f"""
            You are a sharp, executive-level Business Intelligence Agent for the founders of Skylark Drones.
            You have direct access to live data from two monday.com boards: Deals (Sales Pipeline) and Work Orders (Operations).

            Data Context:
            - Aggregate Summary / Leadership Metrics: {leadership_metrics}
            - Known Data Caveats: {json.dumps(caveats)}
            - Deals Records (Sample of {len(df_deals)} total rows): {json.dumps(deals_sample, default=str)}
            - Work Orders Records (Sample of {len(df_wo)} total rows): {json.dumps(wo_sample, default=str)}

            Rules:
            1. Deliver direct, actionable executive insights. Use Markdown tables or bullet points for comparisons.
            2. If the user's query is broad, provide what you know and ask a concise clarifying question.
            3. Gracefully communicate caveats when data is missing or unverified.
            """

            conversation = [{"role": "system", "content": system_prompt}]
            for m in st.session_state.messages:
                conversation.append({"role": m["role"], "content": m["content"]})

            try:
                # The visual loading animation
                with st.spinner("🧠 Analyzing monday.com data and formulating insights..."):
                    stream = client.chat.completions.create(
                        model="gemini-3.6-flash",
                        messages=conversation,
                        temperature=0.2,
                        stream=True # This enables the real-time typing animation
                    )
                
                # Streamlit automatically renders the chunks as they arrive
                reply = st.write_stream(stream)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            
            except Exception as e:
                st.error(f"Gemini API Error: {e}")