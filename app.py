import sqlite3
from contextlib import closing
from datetime import datetime, date
import streamlit as st

APP_TITLE = "TMJ Task Planner"
DB_PATH = "tmj_tasks.db"

st.set_page_config(page_title=APP_TITLE, page_icon="✅", layout="wide")

CUSTOM_CSS = """
<style>
    .main {
        background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    }
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    .tmj-card {
        background: rgba(255,255,255,0.9);
        border: 1px solid rgba(99,102,241,0.10);
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
        border-radius: 20px;
        padding: 18px 20px;
        margin-bottom: 12px;
    }
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f5f7ff 100%);
        border: 1px solid rgba(99,102,241,0.12);
        border-radius: 18px;
        padding: 14px 18px;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }
    .small-label {
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: .04em;
    }
    .big-number {
        color: #0f172a;
        font-size: 1.8rem;
        font-weight: 800;
        margin-top: 4px;
    }
    .hero {
        background: linear-gradient(135deg, #111827 0%, #3730a3 60%, #4f46e5 100%);
        color: white;
        padding: 28px;
        border-radius: 24px;
        box-shadow: 0 18px 40px rgba(55,48,163,0.22);
        margin-bottom: 18px;
    }
    .pill {
        display:inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 6px;
    }
    .pill-high { background:#fee2e2; color:#b91c1c; }
    .pill-open { background:#e0f2fe; color:#075985; }
    .pill-done { background:#dcfce7; color:#166534; }
    .pill-pending { background:#fef3c7; color:#92400e; }
    .task-title {
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
    }
    .muted {
        color:#64748b;
        font-size:0.92rem;
    }
    .login-box {
        max-width: 560px;
        margin: 0 auto;
        padding-top: 2.5rem;
    }
</style>
"""

STATUS_OPTIONS = ["Ongoing", "Pending", "Complete"]
PRIORITY_OPTIONS = ["Normal", "High"]
ROLE_DISPLAY = {"boss": "Robert (Boss)", "tech": "Rahim (Tech)"}


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                outline TEXT,
                requirements TEXT,
                status TEXT NOT NULL DEFAULT 'Ongoing',
                priority TEXT NOT NULL DEFAULT 'Normal',
                assigned_to TEXT NOT NULL DEFAULT 'Rahim',
                created_by TEXT NOT NULL,
                expected_completion TEXT,
                blocker_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.commit()

        users = [
            ("robert", "robert123", "Robert", "boss"),
            ("rahim", "rahim123", "Rahim", "tech"),
        ]
        for user in users:
            cur.execute(
                "INSERT OR IGNORE INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)",
                user,
            )
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM tasks")
        if cur.fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            seed_tasks = [
                (
                    "Build task update dashboard",
                    "Create the main Streamlit dashboard for TMJ Task Planner with login, task list, and filters.",
                    "Professional layout, role-based access, task cards, quick status tracking.",
                    "Ongoing",
                    "High",
                    "Rahim",
                    "Robert",
                    (date.today()).isoformat(),
                    "",
                    now,
                    now,
                ),
                (
                    "Database structure finalization",
                    "Set up SQLite tables for users, tasks, and ongoing feedback history.",
                    "Stable schema, easy updates, portable database file for deployment.",
                    "Pending",
                    "Normal",
                    "Rahim",
                    "Robert",
                    (date.today()).isoformat(),
                    "Waiting for confirmation on final fields to track.",
                    now,
                    now,
                ),
            ]
            cur.executemany(
                """
                INSERT INTO tasks (
                    title, outline, requirements, status, priority, assigned_to, created_by,
                    expected_completion, blocker_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed_tasks,
            )
            conn.commit()
            cur.execute(
                "INSERT INTO feedback (task_id, author, comment, created_at) VALUES (1, 'Robert', 'Please keep the dashboard very polished and easy to review.', ?)",
                (now,),
            )
            cur.execute(
                "INSERT INTO feedback (task_id, author, comment, created_at) VALUES (1, 'Rahim', 'Started layout and database integration.', ?)",
                (now,),
            )
            conn.commit()


def fetch_user(username, password):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, full_name, role FROM users WHERE username = ? AND password = ?",
            (username, password),
        )
        return cur.fetchone()


def fetch_tasks(status_filter="All", priority_filter="All", search_text=""):
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    if status_filter != "All":
        query += " AND status = ?"
        params.append(status_filter)
    if priority_filter != "All":
        query += " AND priority = ?"
        params.append(priority_filter)
    if search_text.strip():
        query += " AND (title LIKE ? OR outline LIKE ? OR requirements LIKE ? OR assigned_to LIKE ?)"
        like = f"%{search_text.strip()}%"
        params.extend([like, like, like, like])
    query += " ORDER BY CASE priority WHEN 'High' THEN 0 ELSE 1 END, updated_at DESC"
    with closing(get_conn()) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()


def fetch_task(task_id):
    with closing(get_conn()) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return cur.fetchone()


def fetch_feedback(task_id):
    with closing(get_conn()) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM feedback WHERE task_id = ? ORDER BY created_at DESC", (task_id,))
        return cur.fetchall()


def add_task(title, outline, requirements, assigned_to, created_by, status, priority, expected_completion, blocker_reason):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tasks (
                title, outline, requirements, status, priority, assigned_to, created_by,
                expected_completion, blocker_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title, outline, requirements, status, priority, assigned_to, created_by,
                expected_completion, blocker_reason, now, now,
            ),
        )
        conn.commit()


def update_task(task_id, status, priority, expected_completion, blocker_reason, title, outline, requirements, assigned_to):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tasks
            SET title = ?, outline = ?, requirements = ?, status = ?, priority = ?,
                assigned_to = ?, expected_completion = ?, blocker_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, outline, requirements, status, priority, assigned_to, expected_completion, blocker_reason, now, task_id),
        )
        conn.commit()


def add_feedback(task_id, author, comment):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feedback (task_id, author, comment, created_at) VALUES (?, ?, ?, ?)",
            (task_id, author, comment, now),
        )
        conn.commit()


def metrics(tasks):
    total = len(tasks)
    ongoing = sum(1 for t in tasks if t["status"] == "Ongoing")
    pending = sum(1 for t in tasks if t["status"] == "Pending")
    completed = sum(1 for t in tasks if t["status"] == "Complete")
    high = sum(1 for t in tasks if t["priority"] == "High")
    return total, ongoing, pending, completed, high


def render_metric(label, value):
    st.markdown(f"<div class='metric-card'><div class='small-label'>{label}</div><div class='big-number'>{value}</div></div>", unsafe_allow_html=True)


def login_screen():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class='hero'>
            <div style='font-size:0.9rem; opacity:0.88;'>TMJ Productivity Suite</div>
            <div style='font-size:2rem; font-weight:800; margin-top:6px;'>{APP_TITLE}</div>
            <div style='margin-top:8px; opacity:0.9;'>A clean and professional task planning workspace for Robert and Rahim.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("login_form"):
        st.subheader("Sign in")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            user = fetch_user(username.strip(), password.strip())
            if user:
                st.session_state.user = {
                    "username": user[0],
                    "full_name": user[1],
                    "role": user[2],
                }
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.info("Available users: Robert and Rahim")
    st.markdown("</div>", unsafe_allow_html=True)


def main_app():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    user = st.session_state.user

    top1, top2 = st.columns([5, 1])
    with top1:
        st.markdown(
            f"""
            <div class='hero'>
                <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap;'>
                    <div>
                        <div style='font-size:0.9rem; opacity:0.88;'>Welcome back</div>
                        <div style='font-size:2rem; font-weight:800; margin-top:4px;'>{user['full_name']}</div>
                        <div style='margin-top:8px; opacity:0.92;'>Track task progress, update blockers, manage deadlines, and keep feedback in one place.</div>
                    </div>
                    <div style='background:rgba(255,255,255,0.12); padding:14px 18px; border-radius:16px; min-width:220px;'>
                        <div style='font-size:0.82rem; opacity:0.85;'>Role</div>
                        <div style='font-size:1.15rem; font-weight:700; margin-top:4px;'>{ROLE_DISPLAY[user['role']]}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with top2:
        st.write("")
        if st.button("Logout", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()

    with st.sidebar:
        st.header("Filters")
        status_filter = st.selectbox("Status", ["All"] + STATUS_OPTIONS)
        priority_filter = st.selectbox("Priority", ["All"] + PRIORITY_OPTIONS)
        search_text = st.text_input("Search")
        st.divider()
        st.subheader("Create New Task")
        with st.form("create_task_form", clear_on_submit=True):
            title = st.text_input("Task title")
            outline = st.text_area("Task outline", height=90)
            requirements = st.text_area("Requirements / details", height=110)
            col1, col2 = st.columns(2)
            with col1:
                status = st.selectbox("Initial status", STATUS_OPTIONS, index=0)
                assigned_to = st.selectbox("Assigned to", ["Rahim", "Robert"], index=0)
            with col2:
                priority = st.selectbox("Priority level", PRIORITY_OPTIONS, index=0)
                expected_completion = st.date_input("Expected completion", value=date.today())
            blocker_reason = st.text_area("Blocker / pending reason", height=80)
            create = st.form_submit_button("Add Task", use_container_width=True)
            if create:
                if not title.strip():
                    st.error("Task title is required.")
                else:
                    add_task(
                        title.strip(), outline.strip(), requirements.strip(), assigned_to,
                        user["full_name"], status, priority, str(expected_completion), blocker_reason.strip()
                    )
                    st.success("Task created successfully.")
                    st.rerun()

    tasks = fetch_tasks(status_filter, priority_filter, search_text)
    total, ongoing, pending, completed, high = metrics(tasks)
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        render_metric("Total Tasks", total)
    with m2:
        render_metric("Ongoing", ongoing)
    with m3:
        render_metric("Pending", pending)
    with m4:
        render_metric("Completed", completed)
    with m5:
        render_metric("High Priority", high)

    st.write("")
    left, right = st.columns([1.08, 1])

    with left:
        st.subheader("Task Board")
        if not tasks:
            st.info("No tasks match the selected filters.")
        for task in tasks:
            due = task["expected_completion"] or "—"
            priority_html = "<span class='pill pill-high'>High Priority</span>" if task["priority"] == "High" else ""
            status_class = {
                "Ongoing": "pill-open",
                "Pending": "pill-pending",
                "Complete": "pill-done",
            }[task["status"]]
            st.markdown(
                f"""
                <div class='tmj-card'>
                    <div style='display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap;'>
                        <div>
                            <div class='task-title'>#{task['id']} · {task['title']}</div>
                            <div class='muted' style='margin-top:6px;'>Assigned to: <b>{task['assigned_to']}</b> &nbsp;•&nbsp; Created by: <b>{task['created_by']}</b></div>
                            <div class='muted' style='margin-top:6px;'>Expected completion: <b>{due}</b></div>
                        </div>
                        <div>{priority_html}<span class='pill {status_class}'>{task['status']}</span></div>
                    </div>
                    <div class='muted' style='margin-top:12px;'>{(task['outline'] or 'No outline added yet.')[:220]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Open Task #{task['id']}", key=f"open_{task['id']}", use_container_width=True):
                st.session_state.selected_task_id = task["id"]
                st.rerun()

    with right:
        st.subheader("Task Details")
        selected_task_id = st.session_state.get("selected_task_id")
        if not selected_task_id and tasks:
            selected_task_id = tasks[0]["id"]
            st.session_state.selected_task_id = selected_task_id
        if not selected_task_id:
            st.info("Select a task to view full details and update it.")
            return

        task = fetch_task(selected_task_id)
        if not task:
            st.warning("Selected task could not be found.")
            return

        st.markdown("<div class='tmj-card'>", unsafe_allow_html=True)
        st.markdown(f"### #{task['id']} · {task['title']}")
        st.caption(f"Assigned to {task['assigned_to']} • Created by {task['created_by']} • Last updated {task['updated_at']}")
        with st.form(f"edit_task_{task['id']}"):
            title = st.text_input("Task title", value=task["title"])
            outline = st.text_area("Outline", value=task["outline"] or "", height=100)
            requirements = st.text_area("Requirements / Details", value=task["requirements"] or "", height=120)
            c1, c2 = st.columns(2)
            with c1:
                status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(task["status"]))
                assigned_to = st.selectbox("Assigned to", ["Rahim", "Robert"], index=["Rahim", "Robert"].index(task["assigned_to"]))
            with c2:
                priority = st.selectbox("Priority", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(task["priority"]))
                initial_date = date.fromisoformat(task["expected_completion"]) if task["expected_completion"] else date.today()
                expected_completion = st.date_input("Expected completion", value=initial_date)
            blocker_reason = st.text_area("Pending reason / blocker", value=task["blocker_reason"] or "", height=90)
            save = st.form_submit_button("Save Task Updates", use_container_width=True)
            if save:
                update_task(
                    task["id"], status, priority, str(expected_completion), blocker_reason.strip(),
                    title.strip(), outline.strip(), requirements.strip(), assigned_to
                )
                st.success("Task updated.")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='tmj-card'>", unsafe_allow_html=True)
        st.markdown("#### Feedback")
        with st.form(f"feedback_{task['id']}", clear_on_submit=True):
            comment = st.text_area("Add ongoing feedback / notes", height=100)
            add_note = st.form_submit_button("Post Feedback", use_container_width=True)
            if add_note:
                if comment.strip():
                    add_feedback(task["id"], user["full_name"], comment.strip())
                    st.success("Feedback added.")
                    st.rerun()
                else:
                    st.error("Please enter feedback before posting.")

        feedback_entries = fetch_feedback(task["id"])
        if not feedback_entries:
            st.info("No feedback added yet.")
        else:
            for item in feedback_entries:
                st.markdown(
                    f"""
                    <div style='border:1px solid #e2e8f0; border-radius:14px; padding:12px 14px; margin-bottom:10px; background:#fff;'>
                        <div style='font-weight:700; color:#0f172a;'>{item['author']}</div>
                        <div class='muted' style='margin:4px 0 8px 0;'>{item['created_at']}</div>
                        <div style='color:#111827;'>{item['comment']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)


def main():
    init_db()
    if "user" not in st.session_state:
        login_screen()
    else:
        main_app()


if __name__ == "__main__":
    main()
