def parse_message(msg: str) -> dict:
    result = {"emp_name": None, "emp_id": None, "card_no": None, "direction": None}
    
    # Check for name and ID: Pattern 'Name, ^123456^'
    m = re.search(r"'(.+?),\s*\^(\d+)\^", msg)
    if m:
        result["emp_name"] = m.group(1).strip()
        result["emp_id"]   = m.group(2)
    
    # Check for direction: (IN) or (OUT)
    all_dirs = re.findall(r"\((\w+)\)", msg) # Flexible to find any word in parens
    if all_dirs:
        # Normalize to uppercase IN/OUT
        found_dir = all_dirs[-1].upper()
        if "IN" in found_dir: result["direction"] = "IN"
        elif "OUT" in found_dir: result["direction"] = "OUT"
        
    return result

def load_data(uploaded_file) -> pd.DataFrame:
    df = pd.read_excel(uploaded_file, dtype=str)
    df.columns = df.columns.str.strip()
    
    # 1. Check for basic Column existence
    required = ["Message", "Message Text", "Server Date/Time"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}")
        st.info(f"Columns found in your file: {list(df.columns)}")
        st.stop()

    # 2. Filter for Admitted cards
    df = df[df["Message"].str.strip().str.lower().str.contains("admitted")].copy()
    
    # 3. Handle Date format (trying multiple formats automatically)
    df["timestamp"] = pd.to_datetime(df["Server Date/Time"], errors="coerce")
    if df["timestamp"].isnull().all():
        # Fallback if the date format is very specific
        df["timestamp"] = pd.to_datetime(df["Server Date/Time"], format="%d-%m-%y %H:%M", errors="coerce")
    
    df = df.dropna(subset=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    
    # 4. Parse message text and check results
    parsed = df["Message Text"].apply(parse_message).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), parsed], axis=1)
    
    # DEBUG: If emp_id is all empty, show the user what the script is seeing
    if df["emp_id"].isnull().all():
        st.warning("⚠️ Logic Error: Could not extract Employee IDs from 'Message Text'.")
        st.write("First 3 examples of your 'Message Text' column:")
        st.code(df["Message Text"].head(3).tolist())
        st.stop()

    df = df.dropna(subset=["emp_id", "direction"])
    return df.sort_values(["emp_id", "timestamp"]).reset_index(drop=True)

