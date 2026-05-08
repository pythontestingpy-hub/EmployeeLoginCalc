import streamlit as st
import pandas as pd
import re
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Office Hours Analyser", layout="wide")

def parse_message(msg: str) -> dict:
    if not isinstance(msg, str): return {"emp_name": None, "emp_id": None, "direction": None}
    result = {"emp_name": None, "emp_id": None, "direction": None}
    # Regex to extract Name and ID from the Message Text column
    m = re.search(r"(?:Admitted|Rejected)\s+'(.+?),\s*\^(\d{6,8})\^", msg)
    if m:
        result["emp_name"], result["emp_id"] = m.group(1).strip(), m.group(2)
    
    # Identify direction (IN/OUT)
    all_dirs = re.findall(r"\((IN|OUT)\)", msg)
    if all_dirs: result["direction"] = all_dirs[-1]
    return result

def load_data(uploaded_file) -> pd.DataFrame:
    # Load Excel and clean column names
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    
    # UPDATED: Use 'Message Type' instead of 'Message'
    # We use case-insensitive matching for 'card admitted'
    msg_col = "Message Type" if "Message Type" in df.columns else "Message"
    
    df = df[df[msg_col].str.contains("admitted", case=False, na=False)].copy()
    
    # Convert timestamp and drop invalid dates (fixes the float comparison error)
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], format="%d-%m-%y %H:%M", errors="coerce")
    df = df.dropna(subset=["timestamp"])
    
    df["date"] = df["timestamp"].dt.date
    df["month_year"] = df["timestamp"].dt.strftime('%b %Y')
    
    # Parse the 'Message Text' column for employee details
    parsed = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed], axis=1)
    
    return df.dropna(subset=["emp_id", "direction"]).sort_values("timestamp")

def compute_sessions(events):
    sessions, i = [], 0
    while i < len(events):
        ts, direction = events[i]
        if direction == "IN":
            if i + 1 < len(events) and events[i+1][1] == "OUT":
                sessions.append({"Login": ts, "Logout": events[i+1][0], "Duration": events[i+1][0] - ts})
                i += 2
            else:
                # IN without an OUT
                sessions.append({"Login": ts, "Logout": None, "Duration": pd.Timedelta(0)})
                i += 1
        else:
            # OUT without an IN
            sessions.append({"Login": None, "Logout": ts, "Duration": pd.Timedelta(0)})
            i += 1
    return sessions

def fmt_dur(td):
    if pd.isna(td) or td.total_seconds() <= 0: return "0h 00m"
    total_secs = int(td.total_seconds())
    h, m = divmod(total_secs // 60, 60)
    return f"{h}h {m:02d}m"

# --- STREAMLIT UI ---
st.title("🕒 Employee Office Hours Analyser")

with st.sidebar:
    st.header("Setup")
    uploaded_file = st.file_uploader("Upload Company Access Log (XLSX)", type="xlsx")
    query_date = st.date_input("Select Date", datetime.now())
    search_val = st.text_input("Enter Employee Name or ID")

if uploaded_file and search_val:
    df = load_data(uploaded_file)
    
    # Match user input against ID or Name
    mask = (df["emp_id"] == search_val) | (df["emp_name"].str.contains(search_val, case=False, na=False))
    emp_df = df[mask]

    if not emp_df.empty:
        name = emp_df["emp_name"].iloc[0]
        emp_id = emp_df["emp_id"].iloc[0]
        st.subheader(f"Attendance Dashboard: {name} ({emp_id})")

        # 1. Monthly Summary Logic
        target_month = query_date.strftime('%b %Y')
        month_df = emp_df[emp_df["month_year"] == target_month]
        
        daily_summary = []
        unique_dates = sorted(month_df["date"].unique())
        total_month_seconds = 0
        
        for d in unique_dates:
            day_events = month_df[month_df["date"] == d][["timestamp", "direction"]].values.tolist()
            sessions = compute_sessions(day_events)
            day_total = sum([s["Duration"] for s in sessions], pd.Timedelta(0))
            total_month_seconds += day_total.total_seconds()
            daily_summary.append({
                "Date": d.strftime("%d-%m-%Y"), 
                "Total Hours": fmt_dur(day_total)
            })

        # 2. Display Metrics (Daily vs Monthly)
        col1, col2 = st.columns(2)
        with col1:
            day_str = query_date.strftime("%d-%m-%Y")
            day_total_val = next((item["Total Hours"] for item in daily_summary if item["Date"] == day_str), "0h 00m")
            st.metric(f"Hours on {query_date.strftime('%d %b')}", day_total_val)
        with col2:
            st.metric(f"Grand Total for {target_month}", fmt_dur(pd.Timedelta(seconds=total_month_seconds)))

        # 3. Monthly Breakdown Table
        st.write(f"### 🗓️ Daily Breakdown for {target_month}")
        if daily_summary:
            summary_df = pd.DataFrame(daily_summary)
            st.table(summary_df)
            st.write(f"**Total Monthly Hours Worked: {fmt_dur(pd.Timedelta(seconds=total_month_seconds))}**")
        else:
            st.info("No logs found for the selected month.")
    else:
        st.error("Employee not found. Please check the Name/ID and try again.")
else:
    st.info("Please upload the Excel file and enter an Employee Name or ID to see results.")
