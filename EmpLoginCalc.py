import streamlit as st
import pandas as pd
import re
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Office Hours Analyser", layout="wide")

# --- LOGIC FUNCTIONS ---
def parse_message(msg: str) -> dict:
    result = {"emp_name": None, "emp_id": None, "card_no": None, "direction": None}
    m = re.search(r"(?:Admitted|Rejected)\s+'(.+?),\s*\^(\d{6,8})\^", msg)
    if m:
        result["emp_name"] = m.group(1).strip()
        result["emp_id"]   = m.group(2)
    c = re.search(r"Card:\s*(\d+)", msg)
    if c:
        result["card_no"] = c.group(1)
    all_dirs = re.findall(r"\((IN|OUT)\)", msg)
    if all_dirs:
        result["direction"] = all_dirs[-1]
    return result

def load_data(uploaded_file) -> pd.DataFrame:
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    df = df[df["Message"].str.strip().str.lower() == "card admitted"].copy()
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], format="%d-%m-%y %H:%M", errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["month"] = df["timestamp"].dt.month
    df["year"] = df["timestamp"].dt.year
    parsed = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed], axis=1)
    df = df.dropna(subset=["emp_id", "direction"])
    return df.sort_values(["emp_id", "timestamp"]).reset_index(drop=True)

def compute_sessions(events):
    """Generic session calculator for any list of events"""
    sessions, warnings, i = [], [], 0
    while i < len(events):
        ts, direction = events[i]
        if direction == "IN":
            if i + 1 < len(events) and events[i+1][1] == "OUT":
                sessions.append({"Login": ts, "Logout": events[i+1][0], "Duration": events[i+1][0] - ts, "Note": ""})
                i += 2
            else:
                sessions.append({"Login": ts, "Logout": None, "Duration": None, "Note": "⚠ No logout"})
                warnings.append(f"IN at {ts.strftime('%H:%M')} has no matching OUT")
                i += 1
        else:
            sessions.append({"Login": None, "Logout": ts, "Duration": None, "Note": "⚠ No login"})
            warnings.append(f"OUT at {ts.strftime('%H:%M')} has no preceding IN")
            i += 1
    return sessions, warnings

def fmt_dur(td):
    if td is None or pd.isna(td) or td == pd.Timedelta(0): return "0h 00m"
    total = int(td.total_seconds())
    h, m = divmod(total // 60, 60)
    return f"{h}h {m:02d}m"

# --- STREAMLIT UI ---
st.title("🕒 Employee Office Hours Analyser")

with st.sidebar:
    st.header("Upload & Settings")
    uploaded_file = st.file_uploader("Upload access log (XLSX)", type="xlsx")
    query_date = st.date_input("Select Date", datetime.now())
    search_type = st.radio("Search by:", ["Employee ID", "Employee Name"])
    search_val = st.text_input(f"Enter {search_type}")

if uploaded_file and search_val:
    df = load_data(uploaded_file)
    
    # Identify Employee ID
    emp_id = None
    if search_type == "Employee ID":
        emp_id = search_val.strip()
    else:
        mask = df["emp_name"].str.contains(search_val, case=False, na=False)
        if not df[mask].empty:
            emp_id = df[mask]["emp_id"].iloc[0]

    if emp_id:
        emp_data = df[df["emp_id"] == emp_id]
        
        if not emp_data.empty:
            name = emp_data["emp_name"].iloc[0]
            st.subheader(f"Results for: {name} (ID: {emp_id})")
            
            # --- 1. MONTHLY CALCULATIONS ---
            current_month = query_date.month
            current_year = query_date.year
            month_mask = (emp_data["month"] == current_month) & (emp_data["year"] == current_year)
            month_subset = emp_data[month_mask]
            
            month_events = month_subset[["timestamp", "direction"]].values.tolist()
            month_sessions, _ = compute_sessions(month_events)
            total_month_td = sum([s["Duration"] for s in month_sessions if s["Duration"]], pd.Timedelta(0))
            
            # --- 2. DAILY CALCULATIONS ---
            day_subset = emp_data[emp_data["date"] == query_date]
            day_events = day_subset[["timestamp", "direction"]].values.tolist()
            day_sessions, day_warnings = compute_sessions(day_events)
            total_day_td = sum([s["Duration"] for s in day_sessions if s["Duration"]], pd.Timedelta(0))

            # --- DISPLAY METRICS ---
            col1, col2 = st.columns(2)
            with col1:
                st.metric(f"Hours on {query_date.strftime('%d %b')}", fmt_dur(total_day_td))
            with col2:
                st.metric(f"Total for {query_date.strftime('%B %Y')}", fmt_dur(total_month_td))

            # --- DAILY TABLE ---
            st.write(f"#### Log Details for {query_date.strftime('%d %b %Y')}")
            if day_sessions:
                display_data = []
                for s in day_sessions:
                    display_data.append({
                        "Login": s["Login"].strftime("%H:%M") if s["Login"] else "—",
                        "Logout": s["Logout"].strftime("%H:%M") if s["Logout"] else "—",
                        "Duration": fmt_dur(s["Duration"]),
                        "Note": s["Note"]
                    })
                st.table(pd.DataFrame(display_data))
            else:
                st.warning("No records found for the specific day selected.")
            
            if day_warnings:
                with st.expander("⚠ View Day Warnings"):
                    for w in day_warnings:
                        st.warning(w)
        else:
            st.error("Employee not found in the file.")
    else:
        st.error("Employee not found in the file.")
else:
    st.info("Please upload an Excel file and enter an Employee ID/Name to begin.")
