import streamlit as st
import pandas as pd
from datetime import date
import io
import re
import streamlit.components.v1 as components
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
# 4. UI AND NAVIGATION
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
    menu = st.sidebar.radio("Menu:", ["📊 View List", "➕ Add Employee", "📥 Bulk Import", "✏️ Edit Employee", "🗑️ Delete Employee", "🔍 Duplicate Check", "🛡️ Pending Approvals"])
    if st.sidebar.button("Log Out"):
        st.session_state.role = None
        st.rerun()
else:
    selected_cadre_label = st.sidebar.selectbox("Select your Cadre:", list(CADRES.keys()), key="public_cadre_selector")
    menu = st.sidebar.radio("Menu:", ["📊 View List", "➕ Submit Details", "🔍 Check Status"])
    st.sidebar.info("You are logged in as an Employee.")

selected_cadre_code = CADRES[selected_cadre_label]

full_df = load_all()
if not full_df.empty:
    df = full_df[full_df["cadre"] == selected_cadre_code].copy()
else:
    df = pd.DataFrame()

MIN_DATE = date(1947, 1, 1)

# ==========================================
# 5. MENU LOGIC
# ==========================================

# --- SHARED VIEW LIST (Admin & Public) ---
if menu == "📊 View List":
    st.subheader(f"{selected_cadre_label} Seniority List")
    if df.empty:
        st.info("No employees found.")
    else:
        ranked = compute_seniority(df)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Employees", len(ranked))
        c2.metric("Most Senior", ranked.iloc[0]["name"] if len(ranked) else "—")
        c3.metric("Most Junior", ranked.iloc[-1]["name"] if len(ranked) else "—")

        search = st.text_input("Search list:", "")
        view = ranked.copy()
        if search:
            m = view.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
            view = view[m]

        for date_col in ["dob", "first_apptt", "taking_over", "regular_apptt"]:
            view[date_col] = pd.to_datetime(view[date_col], errors="coerce").dt.strftime('%d %b %Y').fillna("")

        display_cols = ["rank", "name", "father_name", "school", "dob", "first_apptt", "taking_over", "regular_apptt", "desig", "pno", "cnic", "cell", "remarks"]
        
        # --- COPY PROTECTION FOR EMPLOYEES ---
        if st.session_state.role == "public":
            # Aggressive CSS
            st.markdown("""
                <style>
                /* Block selection on the whole page */
                * {
                    -webkit-user-select: none !important;
                    -moz-user-select: none !important;
                    -ms-user-select: none !important;
                    user-select: none !important;
                }
                /* But allow typing in inputs */
                input, textarea {
                    -webkit-user-select: text !important;
                    -moz-user-select: text !important;
                    -ms-user-select: text !important;
                    user-select: text !important;
                }
                </style>
            """, unsafe_allow_html=True)
            
            # JavaScript injection to intercept copy/drag on the table specifically
            components.html(
                """
                <script>
                const preventCopy = (e) => {
                    const target = e.target;
                    if (target.closest('[data-testid="stDataFrame"]')) {
                        e.preventDefault();
                        return false;
                    }
                };
                document.addEventListener('copy', preventCopy, true);
                document.addEventListener('cut', preventCopy, true);
                document.addEventListener('dragstart', preventCopy, true);
                document.addEventListener('selectstart', preventCopy, true);
                </script>
                """,
                height=0, width=0
            )

        st.dataframe(view[display_cols], use_container_width=True, height=600, hide_index=True)
        
        if st.session_state.role == "admin":
            col1, col2 = st.columns(2)
            csv = view[display_cols].to_csv(index=False).encode("utf-8")
            col1.download_button("⬇️ Download CSV", csv, f"{selected_cadre_code}_list.csv", "text/csv")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                view[display_cols].to_excel(writer, index=False)
            col2.download_button("⬇️ Download Excel", buffer.getvalue(), f"{selected_cadre_code}_list.xlsx")

# --- ADMIN-ONLY MENUS ---
elif st.session_state.role == "admin":
    
    if menu == "➕ Add Employee":
        st.subheader(f"Admin: Add New Employee to {selected_cadre_label}")
        live_cnic = st.text_input("CNIC *", key="admin_cnic")
        cnic_in_use = cnic_exists(live_cnic)
        if live_cnic and cnic_in_use: st.error("⚠️ CNIC already exists!")
        form_disabled = bool(live_cnic) and cnic_in_use
        
        with st.form("admin_add"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Name *", disabled=form_disabled)
                father = st.text_input("Father's Name", disabled=form_disabled)
                school = st.text_input("School", disabled=form_disabled)
                default_bps = 12 if selected_cadre_code == "CT-IT" else 15
                bps = st.number_input("BPS", value=default_bps, disabled=form_disabled)
            with c2:
                dob = st.date_input("DOB", value=None, min_value=MIN_DATE, disabled=form_disabled)
                regular = st.date_input("Regular Apptt", value=None, min_value=MIN_DATE, disabled=form_disabled)
                pno = st.text_input("P/No", disabled=form_disabled)
                cell = st.text_input("Cell", disabled=form_disabled)
            
            if st.form_submit_button("Add Employee", disabled=form_disabled):
                if name and live_cnic:
                    rec = (name, father, school, "NSR", bps, "", "", "", "", dob.isoformat() if dob else "", "", "", regular.isoformat() if regular else "", selected_cadre_code, pno, live_cnic, cell, "", selected_cadre_code)
                    submit_employee(rec, is_pending=False)
                    st.success("Added!")
                    st.rerun()

    elif menu == "📥 Bulk Import":
        st.subheader(f"Bulk Import to {selected_cadre_label}")
        template_cols = ["name", "father_name", "school", "district", "bps", "acad", "subject", "dob", "first_apptt", "taking_over", "regular_apptt", "desig", "pno", "cnic", "cell", "remarks"]
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            pd.DataFrame(columns=template_cols).to_excel(writer, index=False)
        st.download_button("⬇️ Download Blank Excel Template", data=buffer.getvalue(), file_name="import_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx"])
        if uploaded_file is not None:
            try:
                import_df = pd.read_excel(uploaded_file, dtype=str).fillna("")
                if ["name", "cnic"] not in import_df.columns:
                    st.error("Missing required columns (name, cnic).")
                else:
                    st.success(f"File loaded. Found {len(import_df)} rows.")
                    if st.button("✅ Process Import"):
                        added, skipped_dup, skipped_err = 0, 0, 0
                        for _, row in import_df.iterrows():
                            cnic = clean_cnic(row.get("cnic", ""))
                            if not cnic or cnic_exists(cnic):
                                skipped_dup += 1
                                continue
                            try:
                                data = {
                                    "name": row.get("name", ""), "father_name": row.get("father_name", ""),
                                    "school": row.get("school", ""), "district": row.get("district", "NSR"),
                                    "bps": int(float(row.get("bps", 15) or 15)), "acad": row.get("acad", ""),
                                    "div": "", "prof": "", "subject": row.get("subject", ""),
                                    "dob": row.get("dob", ""), "first_apptt": row.get("first_apptt", ""),
                                    "taking_over": row.get("taking_over", ""), "regular_apptt": row.get("regular_apptt", ""),
                                    "desig": row.get("desig", selected_cadre_code), "pno": row.get("pno", ""),
                                    "cnic": cnic, "cell": row.get("cell", ""), "remarks": row.get("remarks", ""),
                                    "cadre": selected_cadre_code
                                }
                                supabase.table("employees").insert(data).execute()
                                added += 1
                            except Exception:
                                skipped_err += 1
                        st.success(f"Import Complete! Added: {added} | Skipped Dups: {skipped_dup} | Errors: {skipped_err}")
            except Exception as e:
                st.error(f"Error reading file: {e}")

    elif menu == "✏️ Edit Employee":
        st.subheader(f"Edit Employee ({selected_cadre_label})")
        if df.empty: 
            st.info("No employees to edit.")
        else:
            ranked = compute_seniority(df)
            options = ranked.apply(lambda r: f"#{r['rank']} — {r['name']} ({r['cnic']})", axis=1).tolist()
            choice = st.selectbox("Select employee to edit", options)
            idx = options.index(choice)
            row = ranked.iloc[idx]
            with st.form("edit_form"):
                c1, c2 = st.columns(2)
                with c1:
                    e_name = st.text_input("Name *", value=row["name"])
                    e_father = st.text_input("Father's Name", value=row["father_name"])
                    e_school = st.text_input("School Name", value=row["school"])
                    e_district = st.text_input("District", value=row["district"])
                    e_bps = st.number_input("BPS", min_value=1, max_value=22, value=int(row["bps"]) if row["bps"] else 15)
                    e_desig = st.text_input("Designation", value=row["desig"])
                    e_cnic = st.text_input("CNIC *", value=row["cnic"])
                with c2:
                    e_dob = st.text_input("Date of Birth", value=row["dob"])
                    e_first = st.text_input("Date of 1st Apptt", value=row["first_apptt"])
                    e_taking = st.text_input("Date of Taking Over", value=row["taking_over"])
                    e_regular = st.text_input("Date of Regular Apptt", value=row["regular_apptt"])
                    e_pno = st.text_input("P/No", value=row["pno"])
                    e_cell = st.text_input("Cell No", value=row["cell"])
                e_acad = st.text_input("Academic Qualification", value=row["acad"])
                e_subject = st.text_input("Subject", value=row["subject"])
                e_remarks = st.text_area("Remarks", value=row["remarks"])
                save = st.form_submit_button("💾 Save Changes")
                if save:
                    if clean_cnic(e_cnic) != clean_cnic(row["cnic"]) and cnic_exists(clean_cnic(e_cnic)):
                        st.error("⚠️ This CNIC is already used by another employee.")
                    else:
                        rec = (e_name.strip(), e_father.strip(), e_school.strip(), e_district.strip(), int(e_bps), e_acad.strip(), row["div"], row["prof"], e_subject.strip(), e_dob, e_first, e_taking, e_regular, e_desig, e_pno.strip(), e_cnic.strip(), e_cell.strip(), e_remarks.strip(), row["cadre"])
                        ok, msg = update_employee(int(row["id"]), rec)
                        if ok: st.success(msg); st.rerun()
                        else: st.error(msg)

    elif menu == "🗑️ Delete Employee":
        st.subheader(f"Delete Employee ({selected_cadre_label})")
        if df.empty: 
            st.info("No employees to delete.")
        else:
            ranked = compute_seniority(df)
            options = ranked.apply(lambda r: f"#{r['rank']} — {r['name']} ({r['cnic']})", axis=1).tolist()
            choice = st.selectbox("Select employee to delete", options)
            confirm = st.checkbox("I confirm I want to permanently delete this employee.")
            if st.button("🗑️ Delete permanently", type="secondary", disabled=not confirm):
                idx = options.index(choice)
                delete_employee(int(ranked.iloc[idx]["id"]))
                st.success("Deleted."); st.rerun()

    elif menu == "🔍 Duplicate Check":
        st.subheader(f"🔍 Duplicate Detection ({selected_cadre_label})")
        if df.empty: 
            st.info("No employees to check.")
        else:
            dups = find_duplicates(df)
            if not dups: st.success("✅ No duplicates found.")
            else:
                st.warning(f"⚠️ Found **{len(dups)}** type(s) of duplicate issues.")
                for title, table in dups.items():
                    with st.expander(f"{title} — {len(table)} rows", expanded=False):
                        st.dataframe(table, use_container_width=True)

    elif menu == "🛡️ Pending Approvals":
        st.subheader(f"🛡️ Pending Approvals for {selected_cadre_label}")
        pending_df = load_pending()
        if not pending_df.empty:
            pending_df = pending_df[pending_df["cadre"] == selected_cadre_code]
            
        if pending_df.empty:
            st.success("✅ No pending approvals.")
        else:
            for idx, row in pending_df.iterrows():
                with st.expander(f"👤 {row['name']} ({row['cnic']})"):
                    st.write(f"**School:** {row['school']} | **DOB:** {row['dob']} | **Reg Apptt:** {row['regular_apptt']}")
                    c1, c2 = st.columns(2)
                    if c1.button(f"✅ Approve", key=f"app_{row['id']}"):
                        rec = (row['name'], row['father_name'], row['school'], row['district'], row['bps'], row['acad'], "", "", row['subject'], row['dob'], row['first_apptt'], row['taking_over'], row['regular_apptt'], row['desig'], row['pno'], row['cnic'], row['cell'], row['remarks'], row['cadre'])
                        submit_employee(rec, is_pending=False)
                        delete_pending(row['id'])
                        st.rerun()
                    if c2.button(f"❌ Reject", key=f"rej_{row['id']}"):
                        delete_pending(row['id'])
                        st.rerun()

# --- PUBLIC (EMPLOYEE) MENUS ---
elif st.session_state.role == "public":
    
    if menu == "➕ Submit Details":
        st.subheader(f"Submit Your Details for {selected_cadre_label}")
        st.info("Your data will be reviewed by Admin before being added to the Seniority List.")
        live_cnic = st.text_input("CNIC *", key="pub_cnic")
        cnic_in_use = cnic_exists(live_cnic)
        if live_cnic and cnic_in_use: 
            st.error("⚠️ This CNIC is already in the system.")
        form_disabled = bool(live_cnic) and cnic_in_use
        
        with st.form("pub_add"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Name *", disabled=form_disabled)
                father = st.text_input("Father's Name", disabled=form_disabled)
                school = st.text_input("School", disabled=form_disabled)
                default_bps = 12 if selected_cadre_code == "CT-IT" else 15
                bps = st.number_input("BPS", value=default_bps, disabled=form_disabled)
            with c2:
                dob = st.date_input("DOB", value=None, min_value=MIN_DATE, disabled=form_disabled)
                regular = st.date_input("Regular Apptt", value=None, min_value=MIN_DATE, disabled=form_disabled)
                pno = st.text_input("P/No", disabled=form_disabled)
                cell = st.text_input("Cell", disabled=form_disabled)
            
            if st.form_submit_button("Submit to Admin", disabled=form_disabled):
                if name and live_cnic:
                    rec = (name, father, school, "NSR", bps, "", "", "", "", dob.isoformat() if dob else "", "", "", regular.isoformat() if regular else "", selected_cadre_code, pno, live_cnic, cell, "", selected_cadre_code)
                    submit_employee(rec, is_pending=True)
                    st.success("✅ Submitted! Pending Admin approval.")
                    st.balloons()

    elif menu == "🔍 Check Status":
        st.subheader(f"🔍 Check Your Seniority Status")
        st.write(f"You are checking the **{selected_cadre_label}** list.")
        
        check_cnic = st.text_input("Enter your CNIC")
        if st.button("Search"):
            cleaned_search = clean_cnic(check_cnic)
            if not cleaned_search:
                st.error("Enter a valid CNIC.")
            else:
                employee_record = pd.DataFrame()
                if not df.empty:
                    df_copy = df.copy()
                    df_copy["cnic_clean"] = df_copy["cnic"].apply(clean_cnic)
                    employee_record = df_copy[df_copy["cnic_clean"] == cleaned_search]
                
                pending_record = pd.DataFrame()
                pending_df_all = load_pending()
                if not pending_df_all.empty:
                    pending_copy = pending_df_all[pending_df_all["cadre"] == selected_cadre_code].copy()
                    pending_copy["cnic_clean"] = pending_copy["cnic"].apply(clean_cnic)
                    pending_record = pending_copy[pending_copy["cnic_clean"] == cleaned_search]

                if not employee_record.empty:
                    ranked_df = compute_seniority(df)
                    ranked_copy = ranked_df.copy()
                    ranked_copy["cnic_clean"] = ranked_copy["cnic"].apply(clean_cnic)
                    final_record = ranked_copy[ranked_copy["cnic_clean"] == cleaned_search].iloc[0]
                    
                    st.success("✅ Your record is officially added to the Seniority List.")
                    
                    st.markdown("### 🪪 Official Seniority Snapshot")
                    st.info(f"**{final_record['name']}** s/o {final_record['father_name']}\n\n"
                            f"**School:** {final_record['school']}\n\n"
                            f"**Designation:** {final_record['desig']} (BPS {final_record['bps']})\n\n"
                            f"**Regular Apptt Date:** {final_record['regular_apptt']}")
                    
                    st.metric(label="Your Official Seniority Rank", value=f"#{final_record['rank']}")
                    st.caption("⚠️ This snapshot is generated directly from the official database and cannot be edited or tempered by the user.")
                    
                elif not pending_record.empty:
                    st.warning("⏳ Your record is pending Admin approval.")
                    st.info("Your seniority rank will be displayed here as soon as the Admin verifies it.")
                else:
                    st.error("❌ No record found.")
                    st.write("If you haven't submitted details, go to the **Submit Details** tab.")
