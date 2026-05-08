import streamlit as st
import pandas as pd
import re
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Office Hours Analyser", layout="wide")

# ─────────────────────────────────────────────────────────────
# 1. PARSE MESSAGE TEXT (Updated for Robustness)
# ─────────────────────────────────────────────────────────────
def parse_message(msg: str) -> dict:
    result = {"emp_name": None, "emp_id": None, "card_no": None, "direction": None}
    
    if not isinstance(msg, str):
        return result

    # Pattern: Admitted 'Name, ^123456^
    m = re.search(r"'(.+?),\s*\^(\d+)\^", msg)
    if m:
        result["emp_name"] = m.group(1).strip()
        result["emp_id"]   = m.group(2)
    
    # Flexible Direction Search: looks for (IN) or (OUT) anywhere
    all_dirs = re.findall(r"\((\w+)\)", msg)
    if all_dirs:
        found_dir = all_dirs[-1].upper()
        if "IN" in found_dir: 
            result["direction"] = "IN"
        elif "OUT" in found_dir: 
            result["direction"] = "OUT"
            
    return result

# ─────────────────────────────────────────────────────────────
# 2. LOAD & PREPARE DATA (With Debug Patch)
# ─────────────────────────────────────────────────────────────
def load_data(uploaded_file) -> pd.DataFrame:
    try:
        df = pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")
        st.stop()

    df.columns = df.columns.str.strip()
    
    # Check for required columns
    required = ["Message", "Message Text", "Server Date/Time"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}")
        st.info(f"Available columns: {list(df.columns)}")
        st.stop()

    # Case-insensitive filter for admitted entries
    df = df[df["Message"].str.strip().str.lower().str.contains("admitted", na=False)].copy()
    
    # Smart Date Parsing
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
    if df["timestamp"].isnull().all():
        # Specific fallback format if auto-parse fails
        df["timestamp"] = pd.to_datetime(df["Server Date/Time"], format="%d-%m-%y %H:%M", errors="coerce")
    
    df = df.dropna(subset=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    
    # Parse Message Text
    parsed = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed], axis=1)
    
    # DEBUG CHECK: If no IDs are found, show the raw text to the user
    if df["emp_id"].isnull().all():
        st.warning("⚠️ Could not extract Employee IDs from 'Message Text'.")
        st.subheader("Debug Info: Sample Data from your File")
        st.write("The script is looking for a format like: `'Name, ^ID^`")
        st.write("Here is what your 'Message Text' actually looks like:")
        st.code(df["Message Text"].head(5).tolist())
        st.stop()

    df = df.dropna(subset=["emp_id", "direction"])
    return df.sort_values(["emp_id", "timestamp"]).reset_index(drop=True)

# ─────────────────────────────────────────────────────────────
# 3. COMPUTATION LOGIC
# ─────────────────────────────────────────────────────────────
def compute_sessions(df: pd.DataFrame, emp_id: str, query_date):
    subset = df[(df["emp_id"] == emp_id) & (df["date"] == query_date)].copy()
    if subset.empty:
        return None, [], []
    
    emp_name = subset["emp_name"].iloc[0]
    events = subset[["timestamp", "direction"]].values.tolist()
    sessions, warnings, i = [], [], 0

    while i < len(events):
        ts, direction = events[i]
        if direction == "IN":
            if i + 1 < len(events) and events[i+1][1] == "OUT":
                sessions.append({"Login": ts, "Logout": events[i+1][0], "Duration": events[i+1][0] - ts, "Note": ""})
                i += 2
            else:
                sessions.append({"Login": ts, "Logout": None, "Duration": None, "Note": "⚠ No logout recorded"})
                warnings.append(f"IN at {ts.strftime('%H:%M')} has no matching OUT")
                i += 1
        else:
            sessions.append({"Login": None, "Logout": ts, "Duration": None, "Note": "⚠ No login recorded"})
            warnings.append(f"OUT at {ts.strftime('%H:%M')} has no preceding IN")
            i += 1
    return emp_name, sessions, warnings

def fmt_dur(td):
    if td is None or pd.isna(td): return "—"
    total = int(td.total_seconds())
    h, m = divmod(total // 60, 60)
    return f"{h}h {m:02d}m"

# ─────────────────────────────────────────────────────────────
# 4. STREAMLIT INTERFACE
# ─────────────────────────────────────────────────────────────
st.title("🕒 Employee Office Hours Analyser")

with st.sidebar:
    st.header("Setup")
    uploaded_file = st.file_uploader("Upload Company Access Log (XLSX)", type="xlsx")
    query_date = st.date_input("Analysis Date", datetime.now())
    search_type = st.radio("Search by:", ["Employee ID", "Employee Name"])
    search_val = st.text_input(f"Enter {search_type}")

if uploaded_file and search_val:
    data_df = load_data(uploaded_file)
    
    # Identify Employee ID
    target_id = None
    if search_type == "Employee ID":
        target_id = search_val.strip()
    else:
        mask = data_df["emp_name"].str.contains(search_val, case=False, na=False)
        if not data_df[mask].empty:
            target_id = data_df[mask]["emp_id"].iloc[0]

    if target_id:
        name, sessions, warnings = compute_sessions(data_df, target_id, query_date)
        
        if name:
            st.success(f"Results for: **{name}** (ID: {target_id})")
            
            # Table Creation
            display_list = []
            total_time = pd.Timedelta(0)
            for s in sessions:
                display_list.append({
                    "Login": s["Login"].strftime("%H:%M") if s["Login"] else "—",
                    "Logout": s["Logout"].strftime("%H:%M") if s["Logout"] else "—",
                    "Duration": fmt_dur(s["Duration"]),
                    "Note": s["Note"]
                })
                if s["Duration"]: total_time += s["Duration"]
            
            st.table(pd.DataFrame(display_list))
            st.metric("Total Duration", fmt_dur(total_time))
            
            if warnings:
                with st.expander("Show Log Anomalies"):
                    for w in warnings:
                        st.warning(w)
        else:
            st.error(f"No activity found for {search_val} on {query_date}")
    else:
        st.error("Employee not found. Ensure the name/ID is correct.")
else:
    st.info("👋 Upload your .xlsx file and enter an ID/Name to start.")
