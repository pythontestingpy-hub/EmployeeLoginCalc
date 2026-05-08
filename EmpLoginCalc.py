import streamlit as st
import pandas as pd
import re
from datetime import datetime

st.set_page_config(page_title="Office Hours Analyser", layout="wide")

# ─────────────────────────────────────────────────────────────
# 1. ROBUST PARSER
# ─────────────────────────────────────────────────────────────
def parse_message(msg: str) -> dict:
    result = {"emp_name": "Unknown", "emp_id": None, "direction": None}
    if not isinstance(msg, str): return result

    # Standard Pattern: 'Name, ^ID^'
    m1 = re.search(r"'(.+?),\s*\^(\d+)\^", msg)
    if m1:
        result["emp_name"], result["emp_id"] = m1.group(1).strip(), m1.group(2)
    
    # Direction Search
    if "(IN)" in msg.upper(): result["direction"] = "IN"
    elif "(OUT)" in msg.upper(): result["direction"] = "OUT"
            
    return result

# ─────────────────────────────────────────────────────────────
# 2. DATA ENGINE
# ─────────────────────────────────────────────────────────────
def load_data(uploaded_file):
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    
    # Filter and Parse Dates
    df = df[df["Message"].str.contains("admitted", case=False, na=False)].copy()
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["Month"] = df["timestamp"].dt.strftime('%B %Y')
    
    # Parse Text
    parsed_df = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed_df], axis=1)
    
    # KEYERROR PREVENTER: Ensure columns exist
    for col in ["emp_id", "direction", "emp_name"]:
        if col not in df.columns: df[col] = None

    return df.dropna(subset=["emp_id", "direction"]).sort_values(["emp_id", "timestamp"])

def compute_all_stats(df):
    """Computes totals for every employee in the file"""
    results = []
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
# 3. INTERFACE
# ─────────────────────────────────────────────────────────────
st.title("🕒 Office Hours Master Analyser")

uploaded_file = st.file_uploader("Upload Company Log", type="xlsx")

if uploaded_file:
    full_df = load_data(uploaded_file)
    
    # --- TAB 1: OVERALL SUMMARY ---
    st.header("📋 Full File Summary")
    summary_df = compute_all_stats(full_df)
    
    if not summary_df.empty:
        # Create a readable version of the table
        display_summary = summary_df.copy()
        display_summary["Work Hours"] = display_summary["Total Duration"].apply(fmt_dur)
        
        # Sortable Table
        st.dataframe(
            display_summary[["Month", "Employee ID", "Name", "Work Hours"]].sort_values(["Month", "Name"]),
            use_container_width=True,
            hide_index=True
        )
        
        # Download Button
        csv = display_summary.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download This Summary (CSV)", csv, "office_hours_summary.csv", "text/csv")
    
    st.divider()

    # --- TAB 2: INDIVIDUAL SEARCH ---
    st.header("🔍 Individual Employee Lookup")
    search_val = st.text_input("Enter ID or Name to see daily breakdown")
    
    if search_val:
        target_id = search_val if search_val.isdigit() else None
        if not target_id:
            match = full_df[full_df["emp_name"].str.contains(search_val, case=False, na=False)]
            if not match.empty: target_id = match["emp_id"].iloc[0]

        if target_id:
            emp_data = full_df[full_df["emp_id"] == target_id]
            st.success(f"Detailed Logs for {emp_data['emp_name'].iloc[0]} ({target_id})")
            
            # Monthly metrics for this person
            person_summary = summary_df[summary_df["Employee ID"] == target_id]
            cols = st.columns(len(person_summary))
            for i, (_, row) in enumerate(person_summary.iterrows()):
                cols[i].metric(row["Month"], fmt_dur(row["Total Duration"]))
        else:
            st.error("Employee not found.")
else:
    st.info("Upload an Excel file to generate the full report.")
