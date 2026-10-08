import streamlit as st
import pandas as pd
import libsql_client
from datetime import date, timedelta
import asyncio

st.set_page_config(page_title="Garden Tracker", layout="centered")

# Initialize Turso connection
@st.cache_resource
def get_db():
    url = st.secrets["TURSO_DATABASE_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    return libsql_client.create_client_sync(url=url, auth_token=token)

client = get_db()

# Setup Table (Runs once)
client.execute("""
    CREATE TABLE IF NOT EXISTS treatments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plant_name TEXT,
        treatment TEXT,
        applied_date DATE,
        next_due_date DATE,
        notes TEXT
    )
""")

st.title("🌿 Garden Treatment Tracker")

# 1. Logging Form
with st.expander("Log New Treatment", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        # Changed to multiselect to allow multiple plants
        plants = st.multiselect(
            "Select Plant(s)", 
            ["Hibiscus", "Raat ki Rani", "Parijat", "Mogra", "Champa", "Lemongrass", "Pudina", "Dwarf Kamini","Rajnigandha","Tulasi","Ajwain","Chameli", "Juhi", "Mulabery"],
            default=["Hibiscus"] # Optional: Set a default selection
        )
        applied_on = st.date_input("Applied Date", value=date.today())
        interval_days = st.number_input("Repeat every (days)", min_value=1, value=14)

    with col2:
        treatment = st.selectbox(
            "Treatment Type", 
            ["Neem Oil", "Vermi Compost Tea", "Cow dung tea", "Kitchen compost tea", "Moringa tea", "Saptadhanya tea","banana tea", "onion tea",  "Normal watering"]
        )
        notes = st.text_input("Notes (e.g., dilution ratio, curing state)")

    if st.button("Save Entry", use_container_width=True):
        if not plants:
            st.error("Please select at least one plant.")
        else:
            next_due = applied_on + timedelta(days=interval_days)
            
            # Loop through each selected plant and insert a row
            for plant in plants:
                client.execute(
                    "INSERT INTO treatments (plant_name, treatment, applied_date, next_due_date, notes) VALUES (?, ?, ?, ?, ?)",
                    [plant, treatment, str(applied_on), str(next_due), notes]
                )
            
            st.success(f"Logged treatments for {len(plants)} plant(s)! Next application due: {next_due.strftime('%b %d, %Y')}")
            st.rerun()

# 2. Upcoming Schedule & History
st.subheader("Upcoming Schedule")

# Fetch data
result = client.execute("SELECT * FROM treatments ORDER BY next_due_date ASC")

if result.rows:
    # Convert Turso rows to a Pandas DataFrame for Streamlit display
    df = pd.DataFrame(result.rows, columns=["ID", "Plant", "Treatment", "Applied On", "Next Due", "Notes"])
    
    # Highlight overdue or upcoming treatments
    df['Next Due'] = pd.to_datetime(df['Next Due']).dt.date
    today = date.today()
    
    # Display as a clean dataframe without the ID column
    st.dataframe(
        df.drop(columns=["ID"]), 
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No treatments logged yet.")