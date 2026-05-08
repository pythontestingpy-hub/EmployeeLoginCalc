import streamlit as st
import pandas as pd
import re
from datetime import datetime

# Page Config
st.set_page_config(page_title="Office Hours Analyser", layout="wide")

# ─────────────────────────────────────────────────────────────
# 1. ROBUST DATA PARSER
# ─────────────────────────────────────────────────────────────
def parse_message(msg: str) -> dict:
    result = {"emp_name": "Unknown", "emp_id": None, "direction": None}
    if not isinstance(msg, str): return result

    # Pattern: 'Name, ^ID^'
    m = re.search(r"'(.+?),\s*\^(\d+)\^", msg)
    if m:
        result["emp_name"], result["emp_id"] = m.group(1).strip(), m.group(2)
    
    # Direction: (IN) or (OUT)
    if "(IN)" in msg.upper(): result["direction"] = "IN"
    elif "(OUT)" in msg.upper(): result["direction"] = "OUT"
    return result

def load_data(uploaded_file):
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    
    # Basic filters and date parsing
    df = df[df["Message"].str.contains("admitted", case=False, na=False)].copy()
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["Month"] = df["timestamp"].dt.strftime('%B %Y')
    df["date"] = df["timestamp"].dt.date
    
    # Parse text into columns
    parsed_df = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed_df], axis=1)
    
    # Ensure critical columns exist to prevent KeyError crashes
    for col in ["emp_id", "direction", "emp_name"]:
        if col not in df.columns: df[col] = None

    return df.dropna(subset=["emp_id", "direction"]).sort_values(["emp_id", "timestamp"])

def fmt_dur(td):
    if pd.isna(td) or td.total_seconds() < 0: return "0h 00m"
    total = int(td.total_seconds())
    h, m = divmod(total // 60, 60)
    return f"{h}h {m:02d}m"

# ─────────────────────────────────────────────────────────────
# 2. APPLICATION INTERFACE
# ─────────────────────────────────────────────────────────────
st.title("🕒 Office Hours Master Analyser")

# STEP 1: Upload File
uploaded_file = st.file_uploader("1. Upload Company Log (.xlsx)", type="xlsx")

if uploaded_file:
    # Load and clean data immediately after upload
    full_df = load_data(uploaded_file)
    
    # STEP 2: Input Selection (Sidebar)
    with st.sidebar:
        st.header("Search & Filter")
        
        # Create a list of all employees for the dropdown
        employee_list = full_df[['emp_id', 'emp_name']].drop_duplicates()
        employee_options = ["--- Select Employee ---"] + employee_list.apply(
            lambda x: f"{x['emp_name']} ({x['emp_id']})", axis=1
        ).tolist()
        
        selected_emp = st.selectbox("2. Select Employee (Name or ID)", employee_options)
        
        # Manual Text Input as fallback
        manual_search = st.text_input("Or type ID/Name manually:")

    # STEP 3: Results Display
    if selected_emp != "--- Select Employee ---" or manual_search:
        # Resolve the ID from the selection or manual input
        target_id = None
        if manual_search:
            if manual_search.isdigit(): target_id = manual_search
            else:
                match = full_df[full_df["emp_name"].str.contains(manual_search, case=False, na=False)]
                if not match.empty: target_id = match["emp_id"].iloc[0]
        else:
            target_id = re.search(r"\((\d+)\)", selected_emp).group(1)

        if target_id:
            emp_data = full_df[full_df["emp_id"] == target_id]
            st.header(f"Results for: {emp_data['emp_name'].iloc[0]} ({target_id})")

            # --- MONTHLY SUMMARY ---
            st.subheader("📊 Monthly Totals")
            monthly_durations = []
            for month, group in emp_data.groupby("Month"):
                total_td = pd.Timedelta(0)
                events = group[["timestamp", "direction"]].values.tolist()
                i = 0
                while i < len(events) - 1:
                    if events[i][1] == "IN" and events[i+1][1] == "OUT":
                        total_td += (events[i+1][0] - events[i][0])
                        i += 2
                    else: i += 1
                monthly_durations.append({"Month": month, "Duration": total_td})
            
            m_cols = st.columns(len(monthly_durations))
            for idx, row in enumerate(monthly_durations):
                m_cols[idx].metric(row["Month"], fmt_dur(row["Duration"]))

            st.divider()

            # --- DAILY BREAKDOWN ---
            st.subheader("📅 Daily Breakdown")
            target_date = st.selectbox("Select Date", sorted(emp_data["date"].unique(), reverse=True))
            day_logs = emp_data[emp_data["date"] == target_date]
            
            # Formatting the daily table
            display_day = day_logs[["timestamp", "direction"]].copy()
            display_day["Time"] = display_day["timestamp"].dt.strftime("%H:%M")
            st.table(display_day[["Time", "direction"]])
        else:
            st.error("Employee not found.")
    else:
        # Show Global Summary by default if no one is searched
        st.info("👈 Use the sidebar to search for a specific employee, or view the overall summary below.")
        st.subheader("📋 Overall Office Summary (By Month)")
        
        # Simple global table
        global_summary = []
        for (eid, month, name), group in full_df.groupby(["emp_id", "Month", "emp_name"]):
            total_td = pd.Timedelta(0)
            events = group[["timestamp", "direction"]].values.tolist()
            i = 0
            while i < len(events) - 1:
                if events[i][1] == "IN" and events[i+1][1] == "OUT":
                    total_td += (events[i+1][0] - events[i][0])
                    i += 2
                else: i += 1
            global_summary.append({"Month": month, "ID": eid, "Name": name, "Work Hours": fmt_dur(total_td)})
        
        st.dataframe(pd.DataFrame(global_summary), use_container_width=True, hide_index=True)
else:
    st.info("👋 Welcome! Please upload your access log file to begin.")
