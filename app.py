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

# Check for category column and upgrade table if missing
plant_cols = [col[1] for col in client.execute("PRAGMA table_info(custom_plants)").rows]
if "category" not in plant_cols:
    client.execute("ALTER TABLE custom_plants ADD COLUMN category TEXT DEFAULT '🌸 Flowering'")
    leafy = "('Lemongrass', 'Pudina', 'Tulasi', 'Ajwain')"
    client.execute(f"UPDATE custom_plants SET category = '🌿 Leafy' WHERE name IN {leafy}")

client.execute("UPDATE custom_plants SET category = '🌸 Flowering' WHERE name = 'Mulabery'")

client.execute("""
    CREATE TABLE IF NOT EXISTS custom_treatments (
        name TEXT PRIMARY KEY
    )
""")

# Seed default data if empty
plant_count = client.execute("SELECT COUNT(*) as count FROM custom_plants").rows[0][0]
if plant_count == 0:
    default_plants = {
        "Hibiscus": "🌸 Flowering", "Raat ki Rani": "🌸 Flowering", "Parijat": "🌸 Flowering", 
        "Mogra": "🌸 Flowering", "Champa": "🌸 Flowering", "Lemongrass": "🌿 Leafy", 
        "Pudina": "🌿 Leafy", "Dwarf Kamini": "🌸 Flowering", "Rajnigandha": "🌸 Flowering", 
        "Tulasi": "🌿 Leafy", "Ajwain": "🌿 Leafy", "Chameli": "🌸 Flowering", "Mulabery": "🌸 Flowering"
    }
    for p, cat in default_plants.items():
        client.execute("INSERT OR IGNORE INTO custom_plants (name, category) VALUES (?, ?)", [p, cat])

treatment_count = client.execute("SELECT COUNT(*) as count FROM custom_treatments").rows[0][0]
if treatment_count == 0:
    default_treatments = ["Neem Oil", "Vermi Compost Tea", "Cow dung tea", "Veg/Fruit Peel Compost Tea", "Moringa tea", "Saptadhanya tea", "banana tea", "onion tea", "Normal watering"]
    for t in default_treatments:
        client.execute("INSERT OR IGNORE INTO custom_treatments (name) VALUES (?)", [t])

# --- BULLETPROOF EMOJI MAPPING LOGIC ---
plants_data = client.execute("SELECT name, category FROM custom_plants ORDER BY name ASC").rows
plant_display_map = {row[0]: f"{str(row[1])[0]} {row[0]}" for row in plants_data}
plant_value_map = {v: k for k, v in plant_display_map.items()}
db_plants_display = list(plant_display_map.values())
db_treatments = [row[0] for row in client.execute("SELECT name FROM custom_treatments ORDER BY name ASC").rows]

# Smart mapping function to handle old raw names AND old emoji names
def safe_map_plant(plant_name):
    if not plant_name:
        return ""
    if plant_name in plant_display_map.values(): # Already has emoji
        return plant_name
    if plant_name in plant_display_map: # Needs emoji added
        return plant_display_map[plant_name]
    return plant_name # Fallback

st.title("🌿 Garden Treatment Tracker")

# 1. Logging Form
with st.expander("Log New Treatment", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        plants = st.multiselect(
            "Select Plant(s)", 
            db_plants_display,
            default=[db_plants_display[0]] if db_plants_display else None
        )
        applied_on = st.date_input("Applied Date", value=date.today())
        interval_days = st.number_input("Repeat every (days)", min_value=1, value=14)

    with col2:
        treatment = st.selectbox("Treatment Type", db_treatments)
        notes = st.text_input("Notes (e.g., dilution ratio, curing state)")

    if st.button("Save Entry", use_container_width=True):
        if not plants:
            st.error("Please select at least one plant.")
        else:
            next_due = applied_on + timedelta(days=interval_days)
            for display_plant in plants:
                actual_plant = plant_value_map.get(display_plant, display_plant)
                client.execute(
                    "INSERT INTO treatments (plant_name, treatment, applied_date, next_due_date, notes) VALUES (?, ?, ?, ?, ?)",
                    [actual_plant, treatment, str(applied_on), str(next_due), notes]
                )
            st.success(f"Logged treatments for {len(plants)} plant(s)! Next application due: {next_due.strftime('%b %d, %Y')}")
            st.rerun()

st.divider()

# Tabbed layout for Schedule and Settings
tab1, tab2 = st.tabs(["📅 Upcoming Schedule", "⚙️ Edit Settings & Options"])

with tab1:
    st.subheader("Schedule & History")
    
    # Query treatments table normally without a risky JOIN
    result = client.execute("SELECT id, plant_name as Plant, treatment as Treatment, applied_date as 'Applied On', next_due_date as 'Next Due', notes as Notes FROM treatments ORDER BY next_due_date ASC")
    
    if result.rows:
        df = pd.DataFrame(result.rows, columns=["ID", "Plant", "Treatment", "Applied On", "Next Due", "Notes"])
        
        # Apply the smart mapping function directly to the column
        df['Plant'] = df['Plant'].apply(safe_map_plant)
        
        df['Applied On'] = pd.to_datetime(df['Applied On']).dt.date
        df['Next Due'] = pd.to_datetime(df['Next Due']).dt.date
        df = df.sort_values(by="Next Due", ascending=True)
        
        today = date.today()
        
        def highlight_dates(row):
            due_date = row['Next Due']
            if pd.isna(due_date): return [''] * len(row)
            if due_date < today: return ['background-color: #FFD1DC; color: black'] * len(row)
            elif today <= due_date <= today + timedelta(days=3): return ['background-color: #FFFFE0; color: black'] * len(row)
            else: return [''] * len(row)
        
        styled_df = df.style.apply(highlight_dates, axis=1)
        edit_mode = st.toggle("✏️ Enable Edit Mode")

        if not edit_mode:
            st.dataframe(styled_df, column_config={"ID": None}, use_container_width=True, hide_index=True)
        else:
            edited_df = st.data_editor(
                df, 
                column_config={
                    "ID": None, 
                    "Plant": st.column_config.SelectboxColumn(options=db_plants_display),
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
                
                deleted_ids = original_ids - current_ids
                for del_id in deleted_ids:
                    client.execute("DELETE FROM treatments WHERE id = ?", [del_id])
                    
                for _, row in edited_df.iterrows():
                    row_id = row['ID']
                    p_display = row['Plant']
                    p_name = plant_value_map.get(p_display, p_display) 
                    t_name = row['Treatment']
                    a_date = str(row['Applied On'])
                    n_date = str(row['Next Due'])
                    nts = str(row['Notes']) if pd.notna(row['Notes']) else ""
                    
                    if pd.isna(row_id):
                        client.execute(
                            "INSERT INTO treatments (plant_name, treatment, applied_date, next_due_date, notes) VALUES (?, ?, ?, ?, ?)",
                            [p_name, t_name, a_date, n_date, nts]
                        )
                    else:
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
        new_plant_cat = st.selectbox("Category", ["🌸 Flowering", "🌿 Leafy", "🌳 Tree / Fruiting"])
        
        if st.button("Add Plant"):
            if new_plant:
                client.execute("INSERT OR IGNORE INTO custom_plants (name, category) VALUES (?, ?)", [new_plant, new_plant_cat])
                st.rerun()
                
        plant_to_delete_display = st.selectbox("Remove Plant", db_plants_display)
        if st.button("Delete Plant"):
            actual_plant_to_delete = plant_value_map.get(plant_to_delete_display, plant_to_delete_display)
            client.execute("DELETE FROM custom_plants WHERE name = ?", [actual_plant_to_delete])
            st.rerun()
            
    with colB:
        st.write("**🧪 Treatments**")
        new_treatment = st.text_input("Add New Treatment")
        if st.button("Add Treatment"):