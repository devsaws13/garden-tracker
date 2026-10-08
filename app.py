import streamlit as st
import pandas as pd
import libsql_client
from datetime import date, timedelta

st.set_page_config(page_title="Garden Tracker", layout="centered")

# Initialize Turso connection
@st.cache_resource
def get_db():
    url = st.secrets["TURSO_DATABASE_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    return libsql_client.create_client_sync(url=url, auth_token=token)

client = get_db()

# Setup Tables (Runs once)
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

client.execute("""
    CREATE TABLE IF NOT EXISTS custom_plants (
        name TEXT PRIMARY KEY
    )
""")

client.execute("""
    CREATE TABLE IF NOT EXISTS custom_treatments (
        name TEXT PRIMARY KEY
    )
""")

# Seed default data if empty
plant_count = client.execute("SELECT COUNT(*) as count FROM custom_plants").rows[0][0]
if plant_count == 0:
    default_plants = ["Hibiscus", "Raat ki Rani", "Parijat", "Mogra", "Champa", "Lemongrass", "Pudina", "Dwarf Kamini", "Rajnigandha", "Tulasi", "Ajwain", "Chameli", "Mulabery"]
    for p in default_plants:
        client.execute("INSERT OR IGNORE INTO custom_plants (name) VALUES (?)", [p])

treatment_count = client.execute("SELECT COUNT(*) as count FROM custom_treatments").rows[0][0]
if treatment_count == 0:
    default_treatments = ["Neem Oil", "Vermi Compost Tea", "Cow dung tea", "Veg/Fruit Peel Compost Tea", "Moringa tea", "Saptadhanya tea", "banana tea", "onion tea", "Normal watering"]
    for t in default_treatments:
        client.execute("INSERT OR IGNORE INTO custom_treatments (name) VALUES (?)", [t])

# Fetch dynamic lists
db_plants = [row[0] for row in client.execute("SELECT name FROM custom_plants ORDER BY name ASC").rows]
db_treatments = [row[0] for row in client.execute("SELECT name FROM custom_treatments ORDER BY name ASC").rows]

st.title("🌿 Garden Treatment Tracker")

# 1. Logging Form
with st.expander("Log New Treatment", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        plants = st.multiselect(
            "Select Plant(s)", 
            db_plants,
            default=[db_plants[0]] if db_plants else None
        )
        applied_on = st.date_input("Applied Date", value=date.today())
        interval_days = st.number_input("Repeat every (days)", min_value=1, value=14)

    with col2:
        treatment = st.selectbox(
            "Treatment Type", 
            db_treatments
        )
        notes = st.text_input("Notes (e.g., dilution ratio, curing state)")

    if st.button("Save Entry", use_container_width=True):
        if not plants:
            st.error("Please select at least one plant.")
        else:
            next_due = applied_on + timedelta(days=interval_days)
            for plant in plants:
                client.execute(
                    "INSERT INTO treatments (plant_name, treatment, applied_date, next_due_date, notes) VALUES (?, ?, ?, ?, ?)",
                    [plant, treatment, str(applied_on), str(next_due), notes]
                )
            st.success(f"Logged treatments for {len(plants)} plant(s)! Next application due: {next_due.strftime('%b %d, %Y')}")
            st.rerun()

st.divider()

# Tabbed layout for Schedule and Settings
tab1, tab2 = st.tabs(["📅 Upcoming Schedule", "⚙️ Edit Settings & Options"])

with tab1:
    st.subheader("Schedule & History")
    
    # Fetch data
    result = client.execute("SELECT id, plant_name, treatment, applied_date, next_due_date, notes FROM treatments ORDER BY next_due_date ASC")
    
    if result.rows:
        df = pd.DataFrame(result.rows, columns=["ID", "Plant", "Treatment", "Applied On", "Next Due", "Notes"])
        
        # Convert date strings to actual date objects
        df['Applied On'] = pd.to_datetime(df['Applied On']).dt.date
        df['Next Due'] = pd.to_datetime(df['Next Due']).dt.date
        df = df.sort_values(by="Next Due", ascending=True)
        
        today = date.today()
        
        def highlight_dates(row):
            due_date = row['Next Due']
            if due_date < today:
                return ['background-color: #FFD8A8; color: black'] * len(row)
            elif today <= due_date <= today + timedelta(days=3):
                return ['background-color: #FFD1DC; color: black'] * len(row)
            else:
                return [''] * len(row)
        
        # Display editable dataframe (ID is hidden but kept for database sync)
        edited_df = st.data_editor(
            df.style.apply(highlight_dates, axis=1),
            column_config={
                "ID": None, 
                "Plant": st.column_config.SelectboxColumn(options=db_plants),
                "Treatment": st.column_config.SelectboxColumn(options=db_treatments)
            },
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="log_editor"
        )
        
        if st.button("Save Table Changes", type="primary"):
            original_ids = set(df['ID'].dropna().tolist())
            current_ids = set(edited_df['ID'].dropna().tolist())
            
            # Find and delete rows removed in the editor
            deleted_ids = original_ids - current_ids
            for del_id in deleted_ids:
                client.execute("DELETE FROM treatments WHERE id = ?", [del_id])
                
            # Update existing rows or insert newly typed rows
            for _, row in edited_df.iterrows():
                row_id = row['ID']
                p_name = row['Plant']
                t_name = row['Treatment']
                a_date = str(row['Applied On'])
                n_date = str(row['Next Due'])
                nts = str(row['Notes']) if pd.notna(row['Notes']) else ""
                
                if pd.isna(row_id): # New row added via UI
                    client.execute(
                        "INSERT INTO treatments (plant_name, treatment, applied_date, next_due_date, notes) VALUES (?, ?, ?, ?, ?)",
                        [p_name, t_name, a_date, n_date, nts]
                    )
                else: # Existing row updated
                    client.execute(
                        "UPDATE treatments SET plant_name=?, treatment=?, applied_date=?, next_due_date=?, notes=? WHERE id=?",
                        [p_name, t_name, a_date, n_date, nts, int(row_id)]
                    )
            
            st.success("Log changes saved to database!")
            st.rerun()
    else:
        st.info("No treatments logged yet.")

with tab2:
    st.subheader("Manage Dropdown Options")
    colA, colB = st.columns(2)
    
    with colA:
        st.write("**🌿 Plants**")
        new_plant = st.text_input("Add New Plant")
        if st.button("Add Plant"):
            if new_plant:
                client.execute("INSERT OR IGNORE INTO custom_plants (name) VALUES (?)", [new_plant])
                st.rerun()
                
        plant_to_delete = st.selectbox("Remove Plant", db_plants)
        if st.button("Delete Plant"):
            client.execute("DELETE FROM custom_plants WHERE name = ?", [plant_to_delete])
            st.rerun()
            
    with colB:
        st.write("**🧪 Treatments**")
        new_treatment = st.text_input("Add New Treatment")
        if st.button("Add Treatment"):
            if new_treatment:
                client.execute("INSERT OR IGNORE INTO custom_treatments (name) VALUES (?)", [new_treatment])
                st.rerun()
                
        treatment_to_delete = st.selectbox("Remove Treatment", db_treatments)
        if st.button("Delete Treatment"):
            client.execute("DELETE FROM custom_treatments WHERE name = ?", [treatment_to_delete])
            st.rerun()