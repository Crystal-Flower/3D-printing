import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
import time

# ==========================================
# 1. DATABASE & BACKEND SETUP
# ==========================================

DB_NAME = '3d_printing_system_v2.db'


# Use cache_resource to ensure the DB connection is created only once
# and shared across reruns, preventing "database locked" errors.
@st.cache_resource
def init_db():
    """Initialize the SQLite database with robust schema."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()

    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            email TEXT
        )
    ''')

    # Requests Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            student_name TEXT,
            project_title TEXT,
            duration REAL,
            filament_type TEXT,
            purpose TEXT,
            file_url TEXT,
            mentor_username TEXT,
            status TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            logs TEXT,
            remarks TEXT,
            assigned_technician TEXT
        )
    ''')

    # Machines Table (For Lab In-Charge to manage)
    c.execute('''
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            status TEXT,
            current_job_id INTEGER
        )
    ''')

    # Seed Machines if empty
    c.execute("SELECT count(*) FROM machines")
    if c.fetchone()[0] == 0:
        machines = [('Prusa i3 MK3S #1', 'Available'), ('Prusa i3 MK3S #2', 'Available'),
                    ('Ender 3 V2 #1', 'Maintenance')]
        c.executemany("INSERT INTO machines (name, status) VALUES (?, ?)", machines)

    conn.commit()
    return conn


# Initialize DB connection
conn = init_db()


# ==========================================
# 2. UTILITY FUNCTIONS
# ==========================================

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hash(password, hashed_text):
    return make_hash(password) == hashed_text


def login_user(username, password):
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    if user and check_hash(password, user[2]):
        return user
    return None


def create_user(username, password, role, full_name, email):
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?, ?, ?, ?, ?)',
                  (username, make_hash(password), role, full_name, email))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_all_mentors():
    c = conn.cursor()
    c.execute("SELECT username, full_name FROM users WHERE role='Mentor'")
    return [row[0] for row in c.fetchall()]  # Returning usernames for selection


def log_action(req_id, action, user_name):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {action} by {user_name}\n"
    c = conn.cursor()
    c.execute("SELECT logs FROM requests WHERE id=?", (req_id,))
    current_logs = c.fetchone()[0]
    new_logs = (current_logs or "") + entry
    c.execute("UPDATE requests SET logs = ?, updated_at = ? WHERE id = ?", (new_logs, timestamp, req_id))
    conn.commit()


# ==========================================
# 3. CONSTANTS & CONFIG
# ==========================================

ROLES = ["Student", "Mentor", "Lab In-Charge", "Lab Technician"]

STATUS_OPTS = {
    "PENDING_MENTOR": "Pending Mentor Approval",
    "PENDING_LAB": "Pending Lab In-Charge Approval",
    "APPROVED": "Approved & Scheduled",
    "IN_PROGRESS": "In Progress",
    "COMPLETED": "Completed",
    "REJECTED": "Rejected"
}

st.set_page_config(page_title="3D Print Portal", page_icon="🖨️", layout="wide")


# ==========================================
# 4. AUTHENTICATION VIEWS
# ==========================================

def auth_screen():
    st.title("🖨️ 3D Printing Management System")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        with st.form("login_form"):
            st.subheader("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                user = login_user(username, password)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['user_id'] = user[0]
                    st.session_state['username'] = user[1]
                    st.session_state['role'] = user[3]
                    st.session_state['full_name'] = user[4]
                    st.success(f"Welcome back, {user[4]}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid username or password")

    with tab2:
        with st.form("signup_form"):
            st.subheader("Create New Account")
            new_user = st.text_input("Username")
            new_pass = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ROLES)
            new_name = st.text_input("Full Name")
            new_email = st.text_input("Email")

            submit_reg = st.form_submit_button("Sign Up")

            if submit_reg:
                if len(new_pass) < 4:
                    st.warning("Password must be at least 4 characters.")
                elif create_user(new_user, new_pass, new_role, new_name, new_email):
                    st.success("Account created! Please login.")
                else:
                    st.error("Username already exists.")


# ==========================================
# 5. DASHBOARD VIEWS
# ==========================================

def render_sidebar():
    st.sidebar.title(f"User: {st.session_state['username']}")
    st.sidebar.caption(f"Role: {st.session_state['role']}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()
    st.sidebar.divider()


# --- STUDENT DASHBOARD ---
def student_view():
    st.header("Student Dashboard")

    tab_req, tab_hist = st.tabs(["New Request", "My Requests"])

    with tab_req:
        st.info("Submit a new 3D printing job for approval.")
        with st.form("new_req"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Project Title / Object Name")
                duration = st.number_input("Estimated Hours", min_value=0.5, step=0.5)
                filament = st.radio("Filament Source", ["College-provided", "Own Filament"])
            with col2:
                mentors = get_all_mentors()
                selected_mentor = st.selectbox("Select Mentor", mentors) if mentors else st.text_input(
                    "Mentor Username")
                file_url = st.text_input("Design File URL (Drive/Dropbox)")

            purpose = st.text_area("Purpose & Description")

            submitted = st.form_submit_button("Submit Request")
            if submitted:
                if not title or not purpose or not selected_mentor:
                    st.error("Please fill in Title, Purpose and select a Mentor.")
                else:
                    c = conn.cursor()
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_start = f"[{timestamp}] Submitted by {st.session_state['username']}\n"

                    c.execute('''
                        INSERT INTO requests (student_id, student_name, project_title, duration, filament_type, purpose, file_url, mentor_username, status, created_at, logs)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (st.session_state['user_id'], st.session_state['username'], title, duration, filament, purpose,
                          file_url, selected_mentor, STATUS_OPTS["PENDING_MENTOR"], timestamp, log_start))
                    conn.commit()
                    st.success("Request submitted successfully!")
                    time.sleep(1)
                    st.rerun()

    with tab_hist:
        c = conn.cursor()
        c.execute("SELECT * FROM requests WHERE student_id=? ORDER BY created_at DESC", (st.session_state['user_id'],))
        requests = c.fetchall()

        if not requests:
            st.info("No requests found.")

        for req in requests:
            with st.expander(f"{req[3]} ({req[9]}) - {req[9]}"):
                st.write(f"**Status:** {req[9]}")
                st.write(f"**Mentor:** {req[8]}")
                st.write(f"**Remarks:** {req[13] if req[13] else 'None'}")
                if req[9] == STATUS_OPTS["PENDING_MENTOR"]:
                    if st.button("Cancel Request", key=f"canc_{req[0]}"):
                        c.execute("DELETE FROM requests WHERE id=?", (req[0],))
                        conn.commit()
                        st.rerun()
                st.text_area("Logs", req[12], height=100, disabled=True, key=f"log_{req[0]}")


# --- MENTOR DASHBOARD ---
def mentor_view():
    st.header("Mentor Dashboard")
    st.caption("Review requests assigned to you.")

    c = conn.cursor()
    # Fetch requests pending mentor approval assigned to this mentor
    c.execute("SELECT * FROM requests WHERE mentor_username=? AND status=? ORDER BY created_at DESC",
              (st.session_state['username'], STATUS_OPTS["PENDING_MENTOR"]))
    pending_reqs = c.fetchall()

    if not pending_reqs:
        st.success("No pending requests to review.")

    for req in pending_reqs:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.subheader(req[3])
                st.markdown(f"**Student:** {req[2]} | **Duration:** {req[4]} hrs")
                st.write(f"**Purpose:** {req[6]}")
                if req[7]: st.markdown(f"[View File]({req[7]})")

            with c2:
                st.write("### Actions")
                if st.button("Approve", key=f"mapp_{req[0]}", type="primary"):
                    c.execute("UPDATE requests SET status=? WHERE id=?", (STATUS_OPTS["PENDING_LAB"], req[0]))
                    conn.commit()
                    log_action(req[0], "Approved by Mentor", st.session_state['username'])
                    st.rerun()

                if st.button("Reject", key=f"mrej_{req[0]}"):
                    remarks = st.text_input("Reason for rejection", key=f"mrem_{req[0]}")
                    if st.button("Confirm Reject", key=f"mconf_{req[0]}"):
                        c.execute("UPDATE requests SET status=?, remarks=? WHERE id=?",
                                  (STATUS_OPTS["REJECTED"], remarks, req[0]))
                        conn.commit()
                        log_action(req[0], f"Rejected by Mentor. Reason: {remarks}", st.session_state['username'])
                        st.rerun()


# --- LAB IN-CHARGE DASHBOARD ---
def lab_in_charge_view():
    st.header("Lab In-Charge Dashboard")

    tab_reqs, tab_machines = st.tabs(["Pending Approvals", "Machine Management"])

    with tab_machines:
        st.subheader("Printer Status")
        c = conn.cursor()
        c.execute("SELECT * FROM machines")
        machines = c.fetchall()

        cols = st.columns(3)
        for idx, mac in enumerate(machines):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.write(f"**{mac[1]}**")
                    status_color = "green" if mac[2] == "Available" else "red"
                    st.markdown(f"Status: :{status_color}[{mac[2]}]")

                    new_status = "Maintenance" if mac[2] == "Available" else "Available"
                    if st.button(f"Set {new_status}", key=f"mac_{mac[0]}"):
                        c.execute("UPDATE machines SET status=? WHERE id=?", (new_status, mac[0]))
                        conn.commit()
                        st.rerun()

    with tab_reqs:
        c.execute("SELECT * FROM requests WHERE status=?", (STATUS_OPTS["PENDING_LAB"],))
        reqs = c.fetchall()

        if not reqs:
            st.info("No requests pending lab approval.")

        for req in reqs:
            with st.expander(f"Request #{req[0]}: {req[3]} by {req[2]}", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Filament:** {req[5]}")
                    st.write(f"**Duration:** {req[4]} Hours")
                    st.write(f"**Purpose:** {req[6]}")
                with col2:
                    st.write("**Scheduling**")
                    remark = st.text_input("Lab Remarks (e.g. Assigned Time)", key=f"lrem_{req[0]}")

                    b1, b2 = st.columns(2)
                    if b1.button("Approve & Schedule", key=f"lapp_{req[0]}", type="primary"):
                        c.execute("UPDATE requests SET status=?, remarks=? WHERE id=?",
                                  (STATUS_OPTS["APPROVED"], remark, req[0]))
                        conn.commit()
                        log_action(req[0], "Approved by Lab In-Charge", st.session_state['username'])
                        st.rerun()

                    if b2.button("Reject", key=f"lrej_{req[0]}"):
                        c.execute("UPDATE requests SET status=?, remarks=? WHERE id=?",
                                  (STATUS_OPTS["REJECTED"], remark, req[0]))
                        conn.commit()
                        log_action(req[0], "Rejected by Lab In-Charge", st.session_state['username'])
                        st.rerun()


# --- TECHNICIAN DASHBOARD ---
def technician_view():
    st.header("Technician Dashboard")

    # Filter
    view_filter = st.radio("View:", ["To Do", "In Progress", "Completed History"], horizontal=True)

    status_filter = []
    if view_filter == "To Do":
        status_filter = [STATUS_OPTS["APPROVED"]]
    elif view_filter == "In Progress":
        status_filter = [STATUS_OPTS["IN_PROGRESS"]]
    else:
        status_filter = [STATUS_OPTS["COMPLETED"]]

    c = conn.cursor()
    query = f"SELECT * FROM requests WHERE status IN ({','.join(['?'] * len(status_filter))}) ORDER BY updated_at DESC"
    c.execute(query, status_filter)
    reqs = c.fetchall()

    if not reqs:
        st.info(f"No jobs in '{view_filter}'")

    for req in reqs:
        with st.container(border=True):
            st.markdown(f"### {req[3]}")
            st.caption(f"Student: {req[2]} | Filament: {req[5]}")

            if view_filter == "To Do":
                st.info(f"Scheduled/Remarks: {req[13]}")
                if st.button("Start Job", key=f"start_{req[0]}"):
                    c.execute("UPDATE requests SET status=?, assigned_technician=? WHERE id=?",
                              (STATUS_OPTS["IN_PROGRESS"], st.session_state['username'], req[0]))
                    conn.commit()
                    log_action(req[0], "Job Started", st.session_state['username'])
                    st.rerun()

            elif view_filter == "In Progress":
                st.warning("Printing in progress...")
                final_notes = st.text_input("Final Usage Notes (Weight/Time)", key=f"fin_{req[0]}")
                if st.button("Mark Completed", key=f"done_{req[0]}"):
                    if final_notes:
                        c.execute("UPDATE requests SET status=?, remarks=? WHERE id=?",
                                  (STATUS_OPTS["COMPLETED"], final_notes, req[0]))
                        conn.commit()
                        log_action(req[0], f"Completed. Notes: {final_notes}", st.session_state['username'])
                        st.success("Job moved to history.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Please enter usage notes before completing.")

            elif view_filter == "Completed History":
                st.write(f"**Completed By:** {req[14]}")
                st.write(f"**Final Notes:** {req[13]}")
                st.write(f"**Finished:** {req[11]}")


# ==========================================
# 6. MAIN APP LOGIC
# ==========================================

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    auth_screen()
else:
    render_sidebar()

    role = st.session_state['role']

    if role == "Student":
        student_view()
    elif role == "Mentor":
        mentor_view()
    elif role == "Lab In-Charge":
        lab_in_charge_view()
    elif role == "Lab Technician":
        technician_view()
    else:
        st.error("Unknown Role")