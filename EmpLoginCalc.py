import streamlit as st
import pandas as pd
import re
from datetime import datetime

st.set_page_config(page_title="Work Hours Aggregator", layout="wide")

# ─────────────────────────────────────────────────────────────
# 1. ROBUST PARSER (Direction & ID Logic)
# ─────────────────────────────────────────────────────────────
def parse_message(msg: str) -> dict:
    result = {"emp_id": None, "direction": None}
    if not isinstance(msg, str): return result

    # Standard ID Pattern extraction
    m = re.search(r"\^(\d+)\^", msg)
    if m:
        result["emp_id"] = m.group(1)
    
    # Flexible Direction Search
    if "(IN)" in msg.upper(): result["direction"] = "IN"
    elif "(OUT)" in msg.upper(): result["direction"] = "OUT"
    return result

# ─────────────────────────────────────────────────────────────
# 2. MULTI-FILE ROBUST LOADING
# ─────────────────────────────────────────────────────────────
def load_and_combine(uploaded_files):
    all_data = []
    
    for uploaded_file in uploaded_files:
        # Robust read: handles empty columns/rows at start
        df = pd.read_excel(uploaded_file, dtype=str).dropna(how='all', axis=1).dropna(how='all', axis=0)
        df.columns = df.columns.str.strip()
        
        # Flex Column Selection: 'Message' or 'Message type'
        msg_col = next((c for c in df.columns if c.lower() in ['message', 'message type']), None)
        
        if msg_col and "Message Text" in df.columns and "Server Date/Time" in df.columns:
            # Filter for admitted cards
            df = df[df[msg_col].str.contains("admitted", case=False, na=False)].copy()
            
            # Date processing
            df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
            df = df.dropna(subset=["timestamp"])
            df["Date"] = df["timestamp"].dt.date
            
            # Parse IDs and Directions
            parsed = df["Message Text"].apply(parse_message).apply(pd.Series)
            df = pd.concat([df.reset_index(drop=True), parsed], axis=1)
            
            # Ensure columns exist to prevent crashes
            if "emp_id" in df.columns and "direction" in df.columns:
                all_data.append(df.dropna(subset=["emp_id", "direction"]))
    
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

def fmt_dur(td):
    if pd.isna(td): return "0h 00m"
    total_secs = int(td.total_seconds())
    h, m = divmod(total_secs // 60, 60)
    return f"{h}h {m:02d}m"

# ─────────────────────────────────────────────────────────────
# 3. UI & OUTPUT
# ─────────────────────────────────────────────────────────────
st.title("🕒 Multi-File Work Hours Aggregator")

# Constraints: Max 4 files
files = st.file_uploader("Upload up to 4 Access Logs", type="xlsx", accept_multiple_files=True)

if files:
    if len(files) > 4:
        st.error("Please upload a maximum of 4 files.")
    else:
        combined_df = load_and_combine(files)
        
        if not combined_df.empty:
            # Selection for specific Employee
            id_list = sorted(combined_df["emp_id"].unique())
            target_id = st.selectbox("Select Employee ID to Analyze", id_list)
            
            if target_id:
                emp_df = combined_df[combined_df["emp_id"] == target_id].sort_values("timestamp")
                
                # Calculate Daily Totals
                daily_results = []
                for date, group in emp_df.groupby("Date"):
                    events = group[["timestamp", "direction"]].values.tolist()
                    daily_total = pd.Timedelta(0)
                    i = 0
                    while i < len(events) - 1:
                        if events[i][1] == "IN" and events[i+1][1] == "OUT":
                            daily_total += (events[i+1][0] - events[i][0])
                            i += 2
                        else: i += 1
                    daily_results.append({"Date": date, "Total Time Logged": daily_total})
                
                # Create Final Table
                final_table = pd.DataFrame(daily_results).sort_values("Date")
                
                # Overall Summary Metric
                grand_total = final_table["Total Time Logged"].sum()
                st.metric("Total Working Hours (All Files)", fmt_dur(grand_total))
                
                # Display 2-Column Table
                display_table = final_table.copy()
                display_table["Total Time Logged"] = display_table["Total Time Logged"].apply(fmt_dur)
                st.subheader("Chronological Log")
                st.table(display_table)
                
                # Downloadable Output
                csv = display_table.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Daily Report (CSV)",
                    data=csv,
                    file_name=f"Employee_{target_id}_Summary.csv",
                    mime="text/csv"
                )
        else:
            st.warning("No valid data found in the uploaded files. Check column names.")
