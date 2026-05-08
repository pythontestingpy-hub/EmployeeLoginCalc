import streamlit as st
import pandas as pd
import re
from datetime import datetime

st.set_page_config(page_title="Office Hours Master Analyser", layout="wide")

# ─────────────────────────────────────────────────────────────
# 1. ROBUST PARSER (Handles "Unknown" formats gracefully)
# ─────────────────────────────────────────────────────────────
def parse_message(msg: str) -> dict:
    result = {"emp_name": "Unknown", "emp_id": None, "direction": None}
    if not isinstance(msg, str): return result

    # Primary Pattern: 'Name, ^ID^'
    m1 = re.search(r"'(.+?),\s*\^(\d+)\^", msg)
    if m1:
        result["emp_name"], result["emp_id"] = m1.group(1).strip(), m1.group(2)
    
    # Direction Search: Case-insensitive (IN) or (OUT)
    if "(IN)" in msg.upper(): result["direction"] = "IN"
    elif "(OUT)" in msg.upper(): result["direction"] = "OUT"
            
    return result

# ─────────────────────────────────────────────────────────────
# 2. ROBUST DATA LOADING ENGINE
# ─────────────────────────────────────────────────────────────
def load_data(uploaded_file):
    # Layer 1: Read and clean headers
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    
    # Layer 2: Filter for valid activity
    df = df[df["Message"].str.contains("admitted", case=False, na=False)].copy()
    
    # Layer 3: Defensive Date Parsing
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["Month"] = df["timestamp"].dt.strftime('%B %Y')
    df["date"] = df["timestamp"].dt.date
    
    # Layer 4: Parse Message Text and ensure column existence
    parsed_df = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed_df], axis=1)
    
    # Ensure critical columns always exist to prevent KeyError
    for col in ["emp_id", "direction", "emp_name"]:
        if col not in df.columns: df[col] = None

    return df.dropna(subset=["emp_id", "direction"]).sort_values(["emp_id", "timestamp"])

# ─────────────────────────────────────────────────────────────
# 3. STATS ENGINE
# ─────────────────────────────────────────────────────────────
def compute_all_stats(df):
    results = []
    # Groups by unique person + month combination
    for (emp_id, month, name), group in df.groupby(["emp_id", "Month", "emp_name"]):
        events = group[["timestamp", "direction"]].values.tolist()
        total_td = pd.Timedelta(0)
        i = 0
        while i < len(events) - 1:
            if events[i][1] == "IN" and events[i+1][1] == "OUT":
                total_td += (events[i+1][0] - events[i][0])
                i += 2
            else: i += 1
        results.append({"Employee ID": emp_id, "Name": name, "Month": month, "Total Duration": total_td})
    return pd.DataFrame(results)

def fmt_dur(td):
    if pd.isna(td): return "0h 00m"
    total = int(td.total_seconds())
    h, m = divmod(total // 60, 60)
    return f"{h}h {m:02d}m"

# ─────────────────────────────────────────────────────────────
# 4. SEARCHABLE INTERFACE
# ─────────────────────────────────────────────────────────────
st.title("🕒 Office Hours Master Analyser")

uploaded_file = st.file_uploader("Upload Company Log (.xlsx)", type="xlsx")

if uploaded_file:
    # 1. Load data with robust patches
    full_df = load_data(uploaded_file)
    
    # 2. Display Global Summary
    st.header("📋 Global Performance Summary")
    summary_df = compute_all_stats(full_df)
    
    if not summary_df.empty:
        display_summary = summary_df.copy()
        display_summary["Work Hours"] = display_summary["Total Duration"].apply(fmt_dur)
        st.dataframe(display_summary[["Month", "Employee ID", "Name", "Work Hours"]], use_container_width=True, hide_index=True)
    
    st.divider()

    # 3. INPUT: Specific Search (ID or Name)
    st.header("🔍 Employee Drill-Down")
    search_input = st.text_input("Search for a specific ID or Name to see daily logs:")
    
    if search_input:
        # Resolve search input to an ID
        target_id = None
        if search_input.isdigit():
            target_id = search_input
        else:
            match = full_df[full_df["emp_name"].str.contains(search_input, case=False, na=False)]
            if not match.empty: target_id = match["emp_id"].iloc[0]

        if target_id:
            emp_data = full_df[full_df["emp_id"] == target_id]
            st.success(f"Viewing detailed data for: **{emp_data['emp_name'].iloc[0]}**")
            
            # Show monthly cards for this person
            person_summary = summary_df[summary_df["Employee ID"] == target_id]
            m_cols = st.columns(len(person_summary))
            for idx, (_, row) in enumerate(person_summary.iterrows()):
                m_cols[idx].metric(row["Month"], fmt_dur(row["Total Duration"]))

            # Select a date to view logs
            target_date = st.selectbox("Pick a date to view clock-in/out times:", sorted(emp_data["date"].unique(), reverse=True))
            day_logs = emp_data[emp_data["date"] == target_date]
            st.table(day_logs[["timestamp", "direction"]].assign(time=lambda x: x["timestamp"].dt.strftime("%H:%M"))[["time", "direction"]])
        else:
            st.error("No employee found matching that name or ID.")
else:
    st.info("Please upload an Excel file to see the full office report.")

