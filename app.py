import streamlit as st
import pandas as pd
from datetime import date
import io
import re
from supabase import create_client, Client

# ==========================================
# HELPER: CNIC CLEANER
# ==========================================
def clean_cnic(cnic):
    if not cnic: return ""
    digits = re.sub(r'\D', '', str(cnic))
    if len(digits) == 13:
        return f"{digits[:5]}-{digits[5:12]}-{digits[12:]}"
    return str(cnic).strip()

# ==========================================
# 1. SECURE LOGIN GATE
# ==========================================
if "role" not in st.session_state:
    st.session_state.role = None

if st.session_state.role is None:
    st.title("🔐 Seniority System Login")
    st.write("Please enter the password provided by the administrator.")
    pwd = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if pwd == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.role = "admin"
            st.rerun()
        elif pwd == st.secrets["PUBLIC_PASSWORD"]:
            st.session_state.role = "public"
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

# ==========================================
# 2. SUPABASE CONNECTION
# ==========================================
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# ==========================================
# 3. DB HELPERS
# ==========================================
def load_all():
    response = supabase.table("employees").select("*").execute()
    if not response.data:
        return pd.DataFrame()
    df = pd.DataFrame(response.data)
    if "cadre" not in df.columns:
        df["cadre"] = "CT" 
    return df

def load_pending():
    response = supabase.table("pending_employees").select("*").execute()
    if not response.data:
        return pd.DataFrame()
    return pd.DataFrame(response.data)

def cnic_exists(cnic):
    cleaned = clean_cnic(cnic)
    if not cleaned: return False
    res1 = supabase.table("employees").select("cnic").execute()
    res2 = supabase.table("pending_employees").select("cnic").execute()
    
    all_cnics = [clean_cnic(x["cnic"]) for x in res1.data if x.get("cnic")]
    all_cnics += [clean_cnic(x["cnic"]) for x in res2.data if x.get("cnic")]
    return cleaned in all_cnics

def compute_seniority(df):
    if df.empty: return df
    for col in ["regular_apptt", "taking_over", "dob"]:
        df[col + "_sort"] = pd.to_datetime(df[col], errors="coerce").dt.date
    df = df.sort_values(by=["regular_apptt_sort", "taking_over_sort", "dob_sort"], na_position="last").reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df

def submit_employee(rec, is_pending=True):
    table = "pending_employees" if is_pending else "employees"
    data = {
        "name": rec[0], "father_name": rec[1], "school": rec[2], "district": rec[3], "bps": rec[4],
        "acad": rec[5], "div": rec[6], "prof": rec[7], "subject": rec[8], "dob": rec[9],
        "first_apptt": rec[10], "taking_over": rec[11], "regular_apptt": rec[12], "desig": rec[13],
        "pno": rec[14], "cnic": clean_cnic(rec[15]), "cell": rec[16], "remarks": rec[17], "cadre": rec[18]
    }
    try:
        supabase.table(table).insert(data).execute()
        return True, "Data submitted successfully!"
    except Exception as e:
        return False, f"Error: {e}"

def update_employee(emp_id, rec):
    data = {
        "name": rec[0], "father_name": rec[1], "school": rec[2], "district": rec[3], "bps": rec[4],
        "acad": rec[5], "div": rec[6], "prof": rec[7], "subject": rec[8], "dob": rec[9],
        "first_apptt": rec[10], "taking_over": rec[11], "regular_apptt": rec[12], "desig": rec[13],
        "pno": rec[14], "cnic": clean_cnic(rec[15]), "cell": rec[16], "remarks": rec[17], "cadre": rec[18]
    }
    try:
        supabase.table("employees").update(data).eq("id", emp_id).execute()
        return True, "Employee updated."
    except Exception as e:
        return False, f"Error: {e}"

def delete_employee(emp_id):
    supabase.table("employees").delete().eq("id", emp_id).execute()

def delete_pending(pending_id):
    supabase.table("pending_employees").delete().eq("id", pending_id).execute()

def find_duplicates(df):
    results = {}
    if df.empty: return results
    df["cnic_clean"] = df["cnic"].apply(clean_cnic)
    d = df[df["cnic_clean"].str.strip() != ""].copy()
    dup = d[d.duplicated(subset=["cnic_clean"], keep=False)].sort_values("cnic_clean")
    if len(dup): results["Same CNIC"] = dup[["name", "father_name", "school", "cnic", "dob", "regular_apptt"]]
    return results

# ==========================================
# 4. UI AND TABS
# ==========================================
st.set_page_config(page_title="Seniority System", page_icon="📋", layout="wide")
st.title("📋 Seniority List Management System")

CADRES = {
    "CT (BPS-15)": "CT",
    "PST (BPS-15)": "PST",
    "Drawing Master (BPS-15)": "DM",
    "TT (BPS-15)": "TT",
    "AT (BPS-15)": "AT",
    "CT (IT) (BPS-12)": "CT-IT"
}

if st.session_state.role == "admin":
    st.sidebar.header("Admin Controls")
    selected_cadre_label = st.sidebar.radio("Select Cadre:", list(CADRES.keys()), key="admin_cadre_selector")
    if st.sidebar.button("Log Out"):
        st.session_state.role = None
        st.rerun()
else:
    selected_cadre_label = st.sidebar.selectbox("Select your Cadre:", list(CADRES.keys()), key="public_cadre_selector")
    st.sidebar.info("You are logged in as an Employee.")

selected_cadre_code = CADRES[selected_cadre_label]

full_df = load_all()
if not full_df.empty:
    df = full_df[full_df["cadre"] == selected_cadre_code].copy()
else:
    df = pd.DataFrame()

MIN_DATE = date(1947, 1, 1)

# --- DEFINE TABS BASED ON ROLE ---
if st.session_state.role == "admin":
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 View List", "➕ Add Employee", "📥 Bulk Import", 
        "✏️ Edit Employee", "🗑️ Delete Employee", "🔍 Duplicate Check", "🛡️ Pending Approvals"
    ])
else:
    # Public users now get TWO tabs
    tab_public_add, tab_public_check = st.tabs(["➕ Submit Your Details", "🔍 Check My Status"])

# ---------- TAB 1: View (Admin) ----------
if st.session_state.role == "admin":
    with tab1:
        if df.empty:
            st.info(f"No employees found for {selected_cadre_label}.")
        else:
            ranked = compute_seniority(df)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Active Employees", len(ranked))
            c2.metric("Highest Seniority", ranked.iloc[0]["name"] if len(ranked) else "—")
            c3.metric("Most Junior", ranked.iloc[-1]["name"] if len(ranked) else "—")

            search = st.text_input("Search by name, school, CNIC, or P/No", "")
            view = ranked.copy()
            if search:
                m = (
                    view["name"].str.contains(search, case=False, na=False)
                    | view["school"].str.contains(search, case=False, na=False)
                    | view["cnic"].str.contains(search, case=False, na=False)
                    | view["pno"].str.contains(search, case=False, na=False)
                )
                view = view[m]

            for date_col in ["dob", "first_apptt", "taking_over", "regular_apptt"]:
                view[date_col] = pd.to_datetime(view[date_col], errors="coerce").dt.strftime('%d %b %Y').fillna("")

            display_cols = ["rank", "name", "father_name", "school", "dob", "first_apptt", "taking_over", "regular_apptt", "desig", "pno", "cnic", "cell", "remarks"]
            
            st.dataframe(
                view[display_cols], use_container_width=True, height=600, hide_index=True,
                column_config={
                    "rank": st.column_config.NumberColumn("Rank", width="small"),
                    "name": st.column_config.TextColumn("Name", width="medium"),
                    "father_name": st.column_config.TextColumn("Father's Name", width="medium"),
                    "school": st.column_config.TextColumn("School", width="large"),
                    "dob": st.column_config.TextColumn("DOB", width="small"),
                    "first_apptt": st.column_config.TextColumn("1st Apptt", width="small"),
                    "taking_over": st.column_config.TextColumn("Taking Over", width="small"),
                    "regular_apptt": st.column_config.TextColumn("Regular Apptt", width="small"),
                    "desig": st.column_config.TextColumn("Desig", width="small"),
                    "pno": st.column_config.TextColumn("P/No", width="small"),
                    "cnic": st.column_config.TextColumn("CNIC", width="medium"),
                    "cell": st.column_config.TextColumn("Cell", width="medium"),
                    "remarks": st.column_config.TextColumn("Remarks", width="medium"),
                }
            )

            col_exp1, col_exp2 = st.columns(2)
            csv = view[display_cols].to_csv(index=False).encode("utf-8")
            col_exp1.download_button(f"⬇️ Download CSV", csv, f"{selected_cadre_code}_list.csv", "text/csv")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                view[display_cols].to_excel(writer, index=False, sheet_name=selected_cadre_code[:31])
            col_exp2.download_button(label=f"⬇️ Download Excel", data=buffer.getvalue(), file_name=f"{selected_cadre_code}_list.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- TAB 2: Add (Admin & Public) ----------
if st.session_state.role == "admin":
    with tab2:
        st.subheader(f"Admin: Add New Employee to {selected_cadre_label} (Direct Entry)")
        
        live_cnic = st.text_input("CNIC (unique) *", key="live_cnic_add")
        cnic_in_use = cnic_exists(live_cnic)
        if live_cnic and cnic_in_use:
            st.error("⚠️ This CNIC already exists in the system (or is pending approval).")
        form_disabled = bool(live_cnic) and cnic_in_use

        with st.form("add_form_admin", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Name *", disabled=form_disabled)
                father = st.text_input("Father's Name", disabled=form_disabled)
                school = st.text_input("School Name", disabled=form_disabled)
                district = st.text_input("District", value="NSR", disabled=form_disabled)
                default_bps = 12 if selected_cadre_code == "CT-IT" else 15
                bps = st.number_input("BPS", min_value=1, max_value=22, value=default_bps, disabled=form_disabled)
                desig = st.text_input("Designation", value=selected_cadre_code, disabled=form_disabled)
            with c2:
                dob = st.date_input("Date of Birth", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                first_apptt = st.date_input("Date of 1st Appointment", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                taking = st.date_input("Date of Taking Over", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                regular = st.date_input("Date of Regular Apptt", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                pno = st.text_input("P/No", disabled=form_disabled)
                cell = st.text_input("Cell No", disabled=form_disabled)
            acad = st.text_input("Academic Qualification", disabled=form_disabled)
            subject = st.text_input("Subject", disabled=form_disabled)
            remarks = st.text_area("Remarks", "", disabled=form_disabled)

            submitted = st.form_submit_button("✅ Add Directly", disabled=form_disabled)
            if submitted:
                cnic_clean = clean_cnic(live_cnic)
                if not name.strip(): st.error("Name is required.")
                elif not cnic_clean: st.error("CNIC is required.")
                elif cnic_exists(cnic_clean): st.error("⚠️ This CNIC already exists.")
                else:
                    rec = (name.strip(), father.strip(), school.strip(), district.strip(), int(bps), acad.strip(), "", "", subject.strip(), dob.isoformat() if dob else "", first_apptt.isoformat() if first_apptt else "", taking.isoformat() if taking else "", regular.isoformat() if regular else "", desig, pno.strip(), cnic_clean, cell.strip(), remarks.strip(), selected_cadre_code)
                    ok, msg = submit_employee(rec, is_pending=False)
                    if ok: st.success("✅ Employee added directly.")
                    else: st.error(msg)
else:
    with tab_public_add:
        st.subheader(f"Submit Your Details for {selected_cadre_label}")
        st.info("Your data will be pending until the Admin verifies it.")

        live_cnic = st.text_input("CNIC (unique) *", key="live_cnic_pub")
        cnic_in_use = cnic_exists(live_cnic)
        if live_cnic and cnic_in_use:
            st.error("⚠️ This CNIC already exists in the system (or is pending).")
        form_disabled = bool(live_cnic) and cnic_in_use

        with st.form("add_form_pub", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Name *", disabled=form_disabled)
                father = st.text_input("Father's Name", disabled=form_disabled)
                school = st.text_input("School Name", disabled=form_disabled)
                district = st.text_input("District", value="NSR", disabled=form_disabled)
                default_bps = 12 if selected_cadre_code == "CT-IT" else 15
                bps = st.number_input("BPS", min_value=1, max_value=22, value=default_bps, disabled=form_disabled)
                desig = st.text_input("Designation", value=selected_cadre_code, disabled=form_disabled)
            with c2:
                dob = st.date_input("Date of Birth", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                first_apptt = st.date_input("Date of 1st Appointment", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                taking = st.date_input("Date of Taking Over", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                regular = st.date_input("Date of Regular Apptt", value=None, min_value=MIN_DATE, max_value=date.today(), disabled=form_disabled)
                pno = st.text_input("P/No", disabled=form_disabled)
                cell = st.text_input("Cell No", disabled=form_disabled)
            acad = st.text_input("Academic Qualification", disabled=form_disabled)
            subject = st.text_input("Subject", disabled=form_disabled)
            remarks = st.text_area("Remarks", "", disabled=form_disabled)

            submitted = st.form_submit_button("✅ Submit", disabled=form_disabled)
            if submitted:
                cnic_clean = clean_cnic(live_cnic)
                if not name.strip(): st.error("Name is required.")
                elif not cnic_clean: st.error("CNIC is required.")
                elif cnic_exists(cnic_clean): st.error("⚠️ This CNIC already exists.")
                else:
                    rec = (name.strip(), father.strip(), school.strip(), district.strip(), int(bps), acad.strip(), "", "", subject.strip(), dob.isoformat() if dob else "", first_apptt.isoformat() if first_apptt else "", taking.isoformat() if taking else "", regular.isoformat() if regular else "", desig, pno.strip(), cnic_clean, cell.strip(), remarks.strip(), selected_cadre_code)
                    ok, msg = submit_employee(rec, is_pending=True)
                    if ok: st.success("✅ Data submitted! Pending Admin approval.")
                    else: st.error(msg)

# ---------- NEW TAB: Check My Status (Public Only) ----------
if st.session_state.role == "public":
    with tab_public_check:
        st.subheader(f"🔍 Check Your Seniority Status")
        st.write(f"You are checking the **{selected_cadre_label}** list.")
        
        check_cnic = st.text_input("Enter your CNIC (with or without dashes)", key="check_cnic_input")
        
        if st.button("Search My Record"):
            cleaned_search = clean_cnic(check_cnic)
            if not cleaned_search:
                st.error("Please enter a valid CNIC.")
            else:
                # 1. Check if they are in the MAIN employee list
                employee_record = pd.DataFrame()
                if not df.empty:
                    df_copy = df.copy()
                    df_copy["cnic_clean"] = df_copy["cnic"].apply(clean_cnic)
                    employee_record = df_copy[df_copy["cnic_clean"] == cleaned_search]
                
                # 2. Check if they are in the PENDING list
                pending_record = pd.DataFrame()
                pending_df_all = load_pending()
                if not pending_df_all.empty:
                    pending_copy = pending_df_all[pending_df_all["cadre"] == selected_cadre_code].copy()
                    pending_copy["cnic_clean"] = pending_copy["cnic"].apply(clean_cnic)
                    pending_record = pending_copy[pending_copy["cnic_clean"] == cleaned_search]

                # --- Display the results ---
                if not employee_record.empty:
                    # They are fully approved and in the list!
                    ranked_df = compute_seniority(df)
                    ranked_copy = ranked_df.copy()
                    ranked_copy["cnic_clean"] = ranked_copy["cnic"].apply(clean_cnic)
                    final_record = ranked_copy[ranked_copy["cnic_clean"] == cleaned_search].iloc[0]
                    
                    st.success("✅ Your record is officially added to the Seniority List.")
                    
                    col1, col2 = st.columns(2)
                    col1.metric("Your Current Seniority Rank", f"#{final_record['rank']}")
                    col2.metric("Regular Appointment Date", str(final_record['regular_apptt']))
                    
                    st.markdown(f"**Name:** {final_record['name']}")
                    st.markdown(f"**School:** {final_record['school']}")
                    st.markdown(f"**Designation:** {final_record['desig']}")
                    
                elif not pending_record.empty:
                    # They submitted it, but admin hasn't approved it yet
                    st.warning("⏳ Your record has been submitted successfully, but it is still **pending Admin approval**.")
                    st.info("Your seniority rank will be calculated and displayed as soon as the Admin verifies your documents.")
                else:
                    # They are nowhere to be found
                    st.error("❌ No record found with this CNIC.")
                    st.write("If you have not yet submitted your details, please go to the **Submit Your Details** tab.")
