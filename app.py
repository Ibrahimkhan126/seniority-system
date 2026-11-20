import streamlit as st
import pandas as pd
from datetime import date
import io
from supabase import create_client, Client

# ==========================================
# 1. PASSWORD GATE
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Restricted Access")
    pwd = st.text_input("Enter Admin Password", type="password")
    if st.button("Login"):
        if pwd == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
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
    # Ensure 'cadre' column exists to prevent KeyError
    if "cadre" not in df.columns:
        df["cadre"] = "CT" 
    return df

def cnic_exists(cnic):
    if not cnic or not str(cnic).strip(): return False
    response = supabase.table("employees").select("id").eq("cnic", str(cnic).strip()).execute()
    return len(response.data) > 0

def compute_seniority(df):
    if df.empty: return df
    for col in ["regular_apptt", "taking_over", "dob"]:
        df[col + "_sort"] = pd.to_datetime(df[col], errors="coerce").dt.date
    df = df.sort_values(by=["regular_apptt_sort", "taking_over_sort", "dob_sort"], na_position="last").reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df

def add_employee(rec):
    data = {
        "name": rec[0], "father_name": rec[1], "school": rec[2], "district": rec[3], "bps": rec[4],
        "acad": rec[5], "div": rec[6], "prof": rec[7], "subject": rec[8], "dob": rec[9],
        "first_apptt": rec[10], "taking_over": rec[11], "regular_apptt": rec[12], "desig": rec[13],
        "pno": rec[14], "cnic": rec[15], "cell": rec[16], "remarks": rec[17], "cadre": rec[18]
    }
    try:
        supabase.table("employees").insert(data).execute()
        return True, "Employee added."
    except Exception as e:
        return False, f"Error: {e}"

def update_employee(emp_id, rec):
    data = {
        "name": rec[0], "father_name": rec[1], "school": rec[2], "district": rec[3], "bps": rec[4],
        "acad": rec[5], "div": rec[6], "prof": rec[7], "subject": rec[8], "dob": rec[9],
        "first_apptt": rec[10], "taking_over": rec[11], "regular_apptt": rec[12], "desig": rec[13],
        "pno": rec[14], "cnic": rec[15], "cell": rec[16], "remarks": rec[17], "cadre": rec[18]
    }
    try:
        supabase.table("employees").update(data).eq("id", emp_id).execute()
        return True, "Employee updated."
    except Exception as e:
        return False, f"Error: {e}"

def delete_employee(emp_id):
    supabase.table("employees").delete().eq("id", emp_id).execute()

def find_duplicates(df):
    results = {}
    if df.empty: return results
    d = df[df["cnic"].str.strip() != ""].copy()
    dup = d[d.duplicated(subset=["cnic"], keep=False)].sort_values("cnic")
    if len(dup): results["Same CNIC"] = dup[["name", "father_name", "school", "cnic", "dob", "regular_apptt"]]
    return results

# ==========================================
# 4. UI AND TABS
# ==========================================
st.set_page_config(page_title="Multi-Cadre Seniority System", page_icon="📋", layout="wide")
st.title("📋 Seniority List Management System")

CADRES = {
    "CT (BPS-15)": "CT",
    "PST (BPS-15)": "PST",
    "Drawing Master (BPS-15)": "DM",
    "TT (BPS-15)": "TT",
    "AT (BPS-15)": "AT",
    "CT (IT) (BPS-12)": "CT-IT"
}

# Sidebar - Only 1 unique radio button
st.sidebar.header("Select Cadre")
selected_cadre_label = st.sidebar.radio(
    "Choose a list to view/edit:", 
    list(CADRES.keys()), 
    key="unique_sidebar_cadre_radio_2026" 
)
selected_cadre_code = CADRES[selected_cadre_label]

st.sidebar.markdown("---")
st.sidebar.caption(f"Viewing data for: **{selected_cadre_label}**")

# Load data and filter by cadre
full_df = load_all()
if not full_df.empty:
    df = full_df[full_df["cadre"] == selected_cadre_code].copy()
else:
    df = pd.DataFrame()

MIN_DATE = date(1947, 1, 1)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 View List",
    "➕ Add Employee",
    "📥 Bulk Import",
    "✏️ Edit Employee",
    "🗑️ Delete Employee",
    "🔍 Duplicate Check",
])

# ---------- TAB 1: View ----------
with tab1:
    if df.empty:
        st.info(f"No employees found for {selected_cadre_label}. Use the Bulk Import tab to add data.")
    else:
        ranked = compute_seniority(df)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Active Employees", len(ranked))
        c2.metric("Highest Seniority", ranked.iloc[0]["name"] if len(ranked) else "—")
        c3.metric("Most Junior", ranked.iloc[-1]["name"] if len(ranked) else "—")

        search = st.text_input("Search by name, school, CNIC, or P/No", "", key="search_tab1")
        view = ranked.copy()
        if search:
            m = (
                view["name"].str.contains(search, case=False, na=False)
                | view["school"].str.contains(search, case=False, na=False)
                | view["cnic"].str.contains(search, case=False, na=False)
                | view["pno"].str.contains(search, case=False, na=False)
            )
            view = view[m]

        display_cols = [
            "rank", "name", "father_name", "school", "dob", "first_apptt",
            "taking_over", "regular_apptt", "desig", "pno", "cnic", "cell", "remarks"
        ]
        st.dataframe(view[display_cols], use_container_width=True, height=500)

        st.markdown("### Export Data")
        col_exp1, col_exp2 = st.columns(2)
        
        csv = view[display_cols].to_csv(index=False).encode("utf-8")
        col_exp1.download_button(f"⬇️ Download CSV", csv, f"{selected_cadre_code}_seniority_list.csv", "text/csv")
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            view[display_cols].to_excel(writer, index=False, sheet_name=selected_cadre_code[:31])
        col_exp2.download_button(
            label=f"⬇️ Download Excel",
            data=buffer.getvalue(),
            file_name=f"{selected_cadre_code}_seniority_list.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ---------- TAB 2: Add ----------
with tab2:
    st.subheader(f"Add New Employee to {selected_cadre_label}")
    live_cnic = st.text_input("CNIC (unique) *", key="live_cnic_add")
    
    cnic_in_use = cnic_exists(live_cnic)
    if live_cnic and cnic_in_use:
        st.error("⚠️ This CNIC already exists in the database.")

    form_disabled = bool(live_cnic) and cnic_in_use

    with st.form("add_form", clear_on_submit=True):
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

        submitted = st.form_submit_button("✅ Add Employee", disabled=form_disabled)
        if submitted:
            cnic_clean = live_cnic.strip()
            if not name.strip(): st.error("Name is required.")
            elif not cnic_clean: st.error("CNIC is required.")
            elif cnic_exists(cnic_clean): st.error("⚠️ This CNIC already exists.")
            else:
                rec = (
                    name.strip(), father.strip(), school.strip(), district.strip(),
                    int(bps), acad.strip(), "", "", subject.strip(),
                    dob.isoformat() if dob else "",
                    first_apptt.isoformat() if first_apptt else "",
                    taking.isoformat() if taking else "",
                    regular.isoformat() if regular else "",
                    desig, pno.strip(), cnic_clean, cell.strip(), remarks.strip(), selected_cadre_code
                )
                ok, msg = add_employee(rec)
                if ok: st.success(msg)
                else: st.error(msg)

# ---------- TAB 3: Bulk Import ----------
with tab3:
    st.subheader(f"Bulk Import to {selected_cadre_label}")
    
    template_cols = ["name", "father_name", "school", "district", "bps", "acad", "subject", "dob", "first_apptt", "taking_over", "regular_apptt", "desig", "pno", "cnic", "cell", "remarks"]
    template_df = pd.DataFrame(columns=template_cols)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        template_df.to_excel(writer, index=False)
    st.download_button("⬇️ Download Blank Excel Template", data=buffer.getvalue(), file_name="import_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx"], key="uploader_tab3")
    if uploaded_file is not None:
        try:
            import_df = pd.read_excel(uploaded_file, dtype=str).fillna("")
            required = ["name", "cnic"]
            missing = [c for c in required if c not in import_df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}")
            else:
                st.success(f"File loaded. Found {len(import_df)} rows.")
                st.dataframe(import_df.head(5))
                
                if st.button("✅ Process Import", key="btn_import_tab3"):
                    added = 0
                    skipped_dup = 0
                    skipped_err = 0
                    for _, row in import_df.iterrows():
                        cnic = row.get("cnic", "").strip()
                        if not cnic:
                            skipped_err += 1
                            continue
                        if cnic_exists(cnic):
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
                    st.success(f"Import Complete! Added: {added} | Skipped Duplicates: {skipped_dup} | Errors: {skipped_err}")
        except Exception as e:
            st.error(f"Error reading file: {e}")

# ---------- TAB 4: Edit ----------
with tab4:
    st.subheader(f"Edit Employee ({selected_cadre_label})")
    if df.empty:
        st.info("No employees to edit.")
    else:
        ranked = compute_seniority(df)
        options = ranked.apply(lambda r: f"#{r['rank']} — {r['name']} ({r['cnic']})", axis=1).tolist()
        choice = st.selectbox("Select employee to edit", options, key="edit_select_tab4")
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
                e_first = st.text_input("Date of 1st Appointment", value=row["first_apptt"])
                e_taking = st.text_input("Date of Taking Over", value=row["taking_over"])
                e_regular = st.text_input("Date of Regular Apptt", value=row["regular_apptt"])
                e_pno = st.text_input("P/No", value=row["pno"])
                e_cell = st.text_input("Cell No", value=row["cell"])
            e_acad = st.text_input("Academic Qualification", value=row["acad"])
            e_subject = st.text_input("Subject", value=row["subject"])
            e_remarks = st.text_area("Remarks", value=row["remarks"])

            save = st.form_submit_button("💾 Save Changes")
            if save:
                if e_cnic.strip() != row["cnic"].strip() and cnic_exists(e_cnic.strip()):
                    st.error("⚠️ This CNIC is already used by another employee.")
                else:
                    rec = (
                        e_name.strip(), e_father.strip(), e_school.strip(), e_district.strip(),
                        int(e_bps), e_acad.strip(), row["div"], row["prof"], e_subject.strip(),
                        e_dob, e_first, e_taking, e_regular,
                        e_desig, e_pno.strip(), e_cnic.strip(), e_cell.strip(), e_remarks.strip(), row["cadre"]
                    )
                    ok, msg = update_employee(int(row["id"]), rec)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# ---------- TAB 5: Delete ----------
with tab5:
    st.subheader(f"Delete Employee ({selected_cadre_label})")
    if df.empty:
        st.info("No employees to delete.")
    else:
        ranked = compute_seniority(df)
        options = ranked.apply(lambda r: f"#{r['rank']} — {r['name']} ({r['cnic']})", axis=1).tolist()
        choice = st.selectbox("Select employee to delete", options, key="del_select_tab5")
        confirm = st.checkbox("I confirm I want to permanently delete this employee.", key="confirm_del_tab5")
        if st.button("🗑️ Delete permanently", type="secondary", disabled=not confirm, key="btn_del_tab5"):
            idx = options.index(choice)
            delete_employee(int(ranked.iloc[idx]["id"]))
            st.success("Deleted. List re-ranked.")
            st.rerun()

# ---------- TAB 6: Duplicate Check ----------
with tab6:
    st.subheader(f"🔍 Duplicate Detection ({selected_cadre_label})")
    if df.empty:
        st.info("No employees to check.")
    else:
        dups = find_duplicates(df)
        if not dups:
            st.success("✅ No duplicate patterns detected in this cadre.")
        else:
            st.warning(f"⚠️ Found **{len(dups)}** type(s) of duplicate issues.")
            for title, table in dups.items():
                with st.expander(f"{title} — {len(table)} rows", expanded=False):
                    st.dataframe(table, use_container_width=True)

st.markdown("---")
st.caption("Multi-Cadre System | Data stored remotely in Supabase")
