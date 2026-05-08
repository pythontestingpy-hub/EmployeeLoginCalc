import streamlit as st
import pandas as pd
import re
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Office Hours Analyser", layout="wide")

# ─────────────────────────────────────────────────────────────
# 1. PARSE MESSAGE TEXT
# ─────────────────────────────────────────────────────────────
def parse_message(msg: str) -> dict:
    result = {"emp_name": None, "emp_id": None, "card_no": None, "direction": None}
    if not isinstance(msg, str): return result

    # Pattern: Admitted 'Name, ^123456^
    m = re.search(r"'(.+?),\s*\^(\d+)\^", msg)
    if m:
        result["emp_name"] = m.group(1).strip()
        result["emp_id"]   = m.group(2)
    
    all_dirs = re.findall(r"\((\w+)\)", msg)
    if all_dirs:
        found_dir = all_dirs[-1].upper()
        if "IN" in found_dir: result["direction"] = "IN"
        elif "OUT" in found_dir: result["direction"] = "OUT"
            
    return result

# ─────────────────────────────────────────────────────────────
# 2. DATA PROCESSING
# ─────────────────────────────────────────────────────────────
def load_data(uploaded_file) -> pd.DataFrame:
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    
    # Basic filters
    df = df[df["Message"].str.strip().str.lower().str.contains("admitted", na=False)].copy()
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    
    # Date helper columns
    df["date"] = df["timestamp"].dt.date
    df["Month"] = df["timestamp"].dt.strftime('%B %Y') # e.g., "May 2026"
    
    # Parse Message Text
    parsed = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed], axis=1)
    
    if df["emp_id"].isnull().all():
        st.warning("⚠️ Could not extract IDs. Check 'Message Text' format.")
        st.stop()

    return df.dropna(subset=["emp_id", "direction"]).sort_values(["emp_id", "timestamp"])

def compute_all_sessions(df):
    """Computes durations for all rows to allow for monthly aggregation"""
    sessions = []
    for emp_id, group in df.groupby("emp_id"):
        events = group[["timestamp", "direction", "Month"]].values.tolist()
        i = 0
        while i < len(events):
            ts, direction, month = events[i]
            if direction == "IN" and i + 1 < len(events) and events[i+1][1] == "OUT":
                sessions.append({"emp_id": emp_id, "Month": month, "Duration": events[i+1][0] - ts})
                i += 2
            else:
                i += 1
    return pd.DataFrame(sessions)

def fmt_dur(td):
    if pd.isna(td): return "0h 00m"
    total = int(td.total_seconds())
    h, m = divmod(total // 60, 60)
    return f"{h}h {m:02d}m"

# ─────────────────────────────────────────────────────────────
# 3. INTERFACE
# ─────────────────────────────────────────────────────────────
st.title("🕒 Office Hours: Daily & Monthly Analyser")

with st.sidebar:
    uploaded_file = st.file_uploader("Upload Company Log", type="xlsx")
    search_val = st.text_input("Enter Employee ID or Name")

if uploaded_file and search_val:
    data_df = load_data(uploaded_file)
    
    # Logic to find the correct Employee ID
    if search_val.isdigit():
        target_id = search_val
    else:
        mask = data_df["emp_name"].str.contains(search_val, case=False, na=False)
        target_id = data_df[mask]["emp_id"].iloc[0] if not data_df[mask].empty else None

    if target_id:
        emp_data = data_df[data_df["emp_id"] == target_id]
        emp_name = emp_data["emp_name"].iloc[0]
        
        st.header(f"Employee: {emp_name} ({target_id})")

        # --- SECTION 1: MONTHLY SUMMARY ---
        st.subheader("📊 Monthly Totals")
        all_sessions = compute_all_sessions(emp_data)
        if not all_sessions.empty:
            # Group by Month and sum the timedeltas
            monthly_summary = all_sessions.groupby("Month")["Duration"].sum().reset_index()
            monthly_summary["Total Hours"] = monthly_summary["Duration"].apply(fmt_dur)
            
            # Display metrics side-by-side
            cols = st.columns(len(monthly_summary))
            for idx, row in monthly_summary.iterrows():
                cols[idx].metric(row["Month"], row["Total Hours"])
        else:
            st.write("No complete sessions found to calculate monthly totals.")

        st.divider()

        # --- SECTION 2: DAILY BREAKDOWN ---
        st.subheader("📅 Daily View")
        available_dates = sorted(emp_data["date"].unique(), reverse=True)
        selected_date = st.selectbox("Select a date to see detailed logs", available_dates)
        
        # (Session logic for the specific day)
        day_events = emp_data[emp_data["date"] == selected_date][["timestamp", "direction"]].values.tolist()
        day_sessions = []
        i, day_total = 0, pd.Timedelta(0)
        
        while i < len(day_events):
            ts, direction = day_events[i]
            if direction == "IN" and i + 1 < len(day_events) and day_events[i+1][1] == "OUT":
                dur = day_events[i+1][0] - ts
                day_sessions.append({"In": ts.strftime("%H:%M"), "Out": day_events[i+1][0].strftime("%H:%M"), "Duration": fmt_dur(dur)})
                day_total += dur
                i += 2
            else:
                day_sessions.append({"In": ts.strftime("%H:%M") if direction == "IN" else "—", 
                                     "Out": ts.strftime("%H:%M") if direction == "OUT" else "—", 
                                     "Duration": "Incomplete"})
                i += 1
        
        st.table(pd.DataFrame(day_sessions))
        st.write(f"**Total for {selected_date}:** {fmt_dur(day_total)}")
    else:
        st.error("Employee not found.")
else:
    st.info("Upload a file to see the Monthly and Daily breakdown.")
