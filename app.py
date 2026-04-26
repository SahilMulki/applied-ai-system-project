import calendar as cal_module
from datetime import date, datetime, timedelta, time

import streamlit as st

from agents import CarePlanAgent, HealthAdvisorAgent
from pawpal_system import Frequency, Owner, Pet, Scheduler, Task, TaskType

TASK_COLORS = {
    TaskType.WALK: "#2d9d78",
    TaskType.FEEDING: "#e07b39",
    TaskType.MEDICINE: "#d64550",
    TaskType.GROOMING: "#8b5cf6",
    TaskType.VET_APPOINTMENT: "#3b82f6",
}

st.set_page_config(page_title="PawPal+", page_icon="", layout="wide")

# --- Custom CSS ---
st.markdown("""
<style>
    [data-testid="stSidebar"] { border-right: 2px solid #E8C8A0; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #8B4513; }
    h1, h2, h3 { color: #8B4513; }
    .stButton > button {
        border-radius: 20px;
        font-weight: 600;
        padding: 0.35rem 1.1rem;
        transition: box-shadow 0.15s ease;
    }
    .stButton > button:hover { box-shadow: 0 2px 8px rgba(212,132,62,0.35); }
    [data-testid="stMetric"] {
        background-color: #FFF4E8;
        border-radius: 12px;
        border: 1px solid #E8C8A0;
        padding: 1rem;
    }
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input { border-radius: 10px; }
    [data-testid="stAlert"] { border-radius: 10px; }
    [data-testid="stChatMessage"] {
        border-radius: 14px;
        padding: 4px 8px;
        margin: 2px 0;
    }
    [data-baseweb="tab-list"] { gap: 6px; }
    [data-baseweb="tab"] { border-radius: 8px 8px 0 0; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# --- Initialize session state ---
for key, default in [
    ("owner", None),
    ("scheduler", None),
    ("care_agent", None),
    ("health_agent", None),
    ("care_messages", []),
    ("health_messages", []),
    ("view", "main"),
    ("selected_pet_name", None),
    ("week_offset", 0),
    ("month_offset", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tasks_for_date(scheduler: Scheduler, target_date: date) -> list[tuple[str, Task]]:
    """Return (pet_name, task) pairs for all pending tasks that fall on target_date."""
    result = []
    today = date.today()
    for pet in scheduler.owner.pets:
        for task in pet.tasks:
            if task.completed:
                continue
            freq = task.frequency
            if freq == Frequency.DAILY:
                result.append((pet.name, task))
            elif freq == Frequency.WEEKLY:
                anchor = task.due_date if task.due_date else today
                if target_date.weekday() == anchor.weekday():
                    result.append((pet.name, task))
            elif freq == Frequency.MONTHLY:
                if task.due_date and target_date.day == task.due_date.day:
                    result.append((pet.name, task))
            elif freq == Frequency.AS_NEEDED:
                if task.due_date == target_date:
                    result.append((pet.name, task))
    return result


def _day_header_html(day: date, today: date) -> str:
    label_top = day.strftime("%a")
    label_bot = str(day.day)
    if day == today:
        return (
            f"<div style='text-align:center;background:#D4843E;color:white;"
            f"border-radius:8px;padding:5px 2px;margin-bottom:6px;'>"
            f"<div style='font-size:0.72rem;'>{label_top}</div>"
            f"<div style='font-size:1.05rem;font-weight:700;'>{label_bot}</div></div>"
        )
    return (
        f"<div style='text-align:center;background:#FFF4E8;color:#4A2E0D;"
        f"border-radius:8px;padding:5px 2px;margin-bottom:6px;'>"
        f"<div style='font-size:0.72rem;'>{label_top}</div>"
        f"<div style='font-size:1.05rem;font-weight:600;'>{label_bot}</div></div>"
    )


def _event_pill_html(task: Task, show_time: bool = True) -> str:
    color = TASK_COLORS.get(task.task_type, "#888888")
    time_prefix = task.preferred_time.strftime("%H:%M ") if (task.preferred_time and show_time) else ""
    return (
        f"<div style='background:{color};color:white;border-radius:5px;"
        f"padding:3px 6px;margin:2px 0;font-size:0.72rem;word-break:break-word;'>"
        f"<span style='opacity:0.85;font-size:0.68rem;'>{time_prefix}</span>{task.description}</div>"
    )


def render_week_view(scheduler: Scheduler) -> None:
    today = date.today()
    week_start = (
        today - timedelta(days=today.weekday())
        + timedelta(weeks=st.session_state.week_offset)
    )
    week_end = week_start + timedelta(days=6)

    c_prev, c_title, c_next, c_tod = st.columns([1, 6, 1, 1])
    with c_prev:
        if st.button("◀", key="wk_prev"):
            st.session_state.week_offset -= 1
            st.rerun()
    with c_title:
        st.markdown(
            f"<h4 style='margin:0;color:#8B4513;'>"
            f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}</h4>",
            unsafe_allow_html=True,
        )
    with c_next:
        if st.button("▶", key="wk_next"):
            st.session_state.week_offset += 1
            st.rerun()
    with c_tod:
        if st.button("Today", key="wk_today"):
            st.session_state.week_offset = 0
            st.rerun()

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    days = [week_start + timedelta(days=i) for i in range(7)]
    cols = st.columns(7)
    for col, day in zip(cols, days):
        pairs = sorted(
            tasks_for_date(scheduler, day),
            key=lambda x: x[1].preferred_time or time(23, 59),
        )
        with col:
            st.markdown(_day_header_html(day, today), unsafe_allow_html=True)
            if pairs:
                for _, task in pairs:
                    st.markdown(_event_pill_html(task), unsafe_allow_html=True)
            else:
                st.markdown(
                    "<div style='text-align:center;color:#ccc;font-size:0.8rem;'>—</div>",
                    unsafe_allow_html=True,
                )


def render_month_view(scheduler: Scheduler) -> None:
    today = date.today()
    raw = today.month - 1 + st.session_state.month_offset
    year = today.year + raw // 12
    month = raw % 12 + 1
    first_day = date(year, month, 1)
    last_day = date(year, month, cal_module.monthrange(year, month)[1])

    c_prev, c_title, c_next, c_tod = st.columns([1, 6, 1, 1])
    with c_prev:
        if st.button("◀", key="mo_prev"):
            st.session_state.month_offset -= 1
            st.rerun()
    with c_title:
        st.markdown(
            f"<h4 style='margin:0;color:#8B4513;'>{first_day.strftime('%B %Y')}</h4>",
            unsafe_allow_html=True,
        )
    with c_next:
        if st.button("▶", key="mo_next"):
            st.session_state.month_offset += 1
            st.rerun()
    with c_tod:
        if st.button("Today", key="mo_today"):
            st.session_state.month_offset = 0
            st.rerun()

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    # Day-of-week headers
    header_cols = st.columns(7)
    for col, name in zip(header_cols, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        with col:
            st.markdown(
                f"<div style='text-align:center;font-weight:600;color:#8B4513;"
                f"padding:4px;border-bottom:2px solid #E8C8A0;margin-bottom:4px;'>{name}</div>",
                unsafe_allow_html=True,
            )

    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = last_day + timedelta(days=6 - last_day.weekday())

    current = grid_start
    while current <= grid_end:
        week_days = [current + timedelta(days=i) for i in range(7)]
        row_cols = st.columns(7)
        for col, day in zip(row_cols, week_days):
            pairs = tasks_for_date(scheduler, day) if day.month == month else []
            in_month = day.month == month
            is_today = day == today
            with col:
                if is_today:
                    date_html = (
                        f"<span style='display:inline-block;background:#D4843E;color:white;"
                        f"border-radius:50%;width:22px;height:22px;text-align:center;"
                        f"line-height:22px;font-size:0.78rem;font-weight:700;'>{day.day}</span>"
                    )
                elif in_month:
                    date_html = f"<span style='font-size:0.8rem;font-weight:600;color:#4A2E0D;'>{day.day}</span>"
                else:
                    date_html = f"<span style='font-size:0.8rem;color:#ccc;'>{day.day}</span>"

                events_html = ""
                for _, task in pairs[:3]:
                    color = TASK_COLORS.get(task.task_type, "#888888")
                    events_html += (
                        f"<div style='background:{color};color:white;border-radius:3px;"
                        f"padding:1px 4px;margin:1px 0;font-size:0.65rem;"
                        f"overflow:hidden;white-space:nowrap;text-overflow:ellipsis;'>"
                        f"{task.description}</div>"
                    )
                if len(pairs) > 3:
                    events_html += f"<div style='font-size:0.65rem;color:#888;'>+{len(pairs)-3} more</div>"

                border = "2px solid #D4843E" if is_today else "1px solid #F0E0C8"
                bg = "#FFFBF5" if in_month else "#F9F9F9"
                st.markdown(
                    f"<div style='background:{bg};border:{border};border-radius:6px;"
                    f"padding:5px;min-height:72px;margin:1px;'>"
                    f"{date_html}{events_html}</div>",
                    unsafe_allow_html=True,
                )
        current += timedelta(weeks=1)


# ---------------------------------------------------------------------------
# Pet detail page
# ---------------------------------------------------------------------------

def render_pet_detail() -> None:
    pet_name = st.session_state.selected_pet_name
    pet = next(
        (p for p in st.session_state.owner.pets if p.name == pet_name), None
    )
    if pet is None:
        st.error("Pet not found.")
        if st.button("Back"):
            st.session_state.view = "main"
            st.rerun()
        return

    if st.button("Back to schedule"):
        st.session_state.view = "main"
        st.rerun()

    st.header(pet.name)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Breed", pet.breed)
    with c2:
        st.metric("Age", f"{pet.age} yr")
    with c3:
        st.metric("Total tasks", len(pet.tasks))

    st.divider()

    # All tasks
    st.subheader("Tasks")
    if pet.tasks:
        st.table([
            {
                "Type": t.task_type.value,
                "Description": t.description,
                "Time": t.preferred_time.strftime("%H:%M") if t.preferred_time else "-",
                "Duration (min)": t.duration,
                "Priority": t.priority,
                "Frequency": t.frequency.value,
                "Due": str(t.due_date) if t.due_date else "-",
                "Done": "Yes" if t.completed else "No",
            }
            for t in pet.tasks
        ])
    else:
        st.info("No tasks assigned yet. Add tasks from the Schedule tab.")

    # Medications
    med_tasks = [t for t in pet.tasks if t.task_type == TaskType.MEDICINE]
    if med_tasks:
        st.divider()
        st.subheader("Medications")
        today = date.today()
        for t in med_tasks:
            overdue = t.due_date and t.due_date < today and not t.completed
            status = "Overdue" if overdue else ("Done" if t.completed else "Pending")
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.write(t.description)
            with col_b:
                st.write(str(t.due_date) if t.due_date else "-")
            with col_c:
                if overdue:
                    st.error(status)
                elif t.completed:
                    st.success(status)
                else:
                    st.info(status)

    # Vet appointments
    vet_tasks = [t for t in pet.tasks if t.task_type == TaskType.VET_APPOINTMENT]
    if vet_tasks:
        st.divider()
        st.subheader("Vet Appointments")
        today = date.today()
        for t in vet_tasks:
            overdue = t.due_date and t.due_date < today and not t.completed
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.write(t.description)
            with col_b:
                st.write(str(t.due_date) if t.due_date else "-")
            with col_c:
                if overdue:
                    st.error("Overdue")
                elif t.completed:
                    st.success("Done")
                else:
                    st.info("Upcoming")

    # Health notes
    if pet.health_notes:
        st.divider()
        st.subheader("Health Notes")
        for note in pet.health_notes:
            st.markdown(f"- {note}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("PawPal+")
    st.caption("Your smart pet care companion")
    st.divider()

    st.subheader("Owner Setup")
    owner_name_input = st.text_input("Your name", placeholder="e.g. Jordan")

    if st.button("Create profile", use_container_width=True):
        if owner_name_input.strip():
            st.session_state.owner = Owner(name=owner_name_input.strip())
            st.session_state.scheduler = Scheduler(owner=st.session_state.owner)
            st.session_state.care_agent = CarePlanAgent(st.session_state.scheduler)
            st.session_state.health_agent = HealthAdvisorAgent(st.session_state.scheduler)
            st.session_state.care_messages = []
            st.session_state.health_messages = []
            st.session_state.view = "main"
            st.session_state.selected_pet_name = None
            st.success(f"Welcome, {owner_name_input.strip()}!")
        else:
            st.warning("Please enter your name first.")

    if st.session_state.owner:
        st.divider()
        st.subheader("Your Pets")

        with st.expander("Add a new pet", expanded=not st.session_state.owner.pets):
            new_pet_name = st.text_input("Pet name", placeholder="e.g. Mochi", key="sidebar_pet_name")
            new_pet_breed = st.text_input("Breed", placeholder="e.g. Shiba Inu", key="sidebar_pet_breed")
            new_pet_age = st.number_input("Age (years)", min_value=0, max_value=30, value=2, key="sidebar_pet_age")

            if st.button("Add pet", use_container_width=True):
                try:
                    pet = Pet(name=new_pet_name, breed=new_pet_breed, age=int(new_pet_age))
                    st.session_state.owner.add_pet(pet)
                    st.session_state.care_agent = CarePlanAgent(st.session_state.scheduler)
                    st.session_state.health_agent = HealthAdvisorAgent(st.session_state.scheduler)
                    st.success(f"{new_pet_name} added!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        for p in st.session_state.owner.pets:
            if st.button(p.name, key=f"pet_nav_{p.name}", use_container_width=True):
                st.session_state.view = "pet_detail"
                st.session_state.selected_pet_name = p.name
                st.rerun()


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

if st.session_state.owner is None:
    st.title("PawPal+")
    st.markdown("### Welcome!")
    st.info("Enter your name in the sidebar to get started.")
    st.stop()

# Pet detail page
if st.session_state.view == "pet_detail":
    render_pet_detail()
    st.stop()

# Main tabs
tab_schedule, tab_care, tab_health = st.tabs(["Schedule", "Care Plan Agent", "Health Advisor"])


# ================================================================
# Schedule tab
# ================================================================
with tab_schedule:
    st.subheader(f"{st.session_state.owner.name}'s Schedule")

    if not st.session_state.owner.pets:
        st.info("Add a pet in the sidebar to get started.")
    else:
        day_tab, week_tab, month_tab = st.tabs(["Today", "This Week", "This Month"])

        # ---- Today ----
        with day_tab:
            st.markdown("#### Add a Task")
            pet_names = [p.name for p in st.session_state.owner.pets]
            selected_pet = st.selectbox("Assign to pet", pet_names)

            col1, col2, col3 = st.columns(3)
            with col1:
                task_title = st.text_input("Task description", placeholder="e.g. Morning walk")
            with col2:
                duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
            with col3:
                priority = st.selectbox("Priority (1=low, 5=high)", [1, 2, 3, 4, 5], index=2)

            col4, col5 = st.columns(2)
            with col4:
                task_type = st.selectbox("Task type", [t.value for t in TaskType])
            with col5:
                preferred_hour = st.number_input("Start hour (0-23)", min_value=0, max_value=23, value=8)

            if st.button("Add task"):
                try:
                    target_pet = next(p for p in st.session_state.owner.pets if p.name == selected_pet)
                    task = Task(
                        task_type=TaskType(task_type),
                        description=task_title,
                        duration=int(duration),
                        priority=priority,
                        frequency=Frequency.DAILY,
                        preferred_time=time(int(preferred_hour), 0),
                    )
                    st.session_state.scheduler.add_task(target_pet, task)
                    st.success(f"'{task_title}' added to {selected_pet}'s schedule.")
                except ValueError as e:
                    st.error(str(e))

            all_tasks = st.session_state.owner.get_all_tasks()
            today_pairs = tasks_for_date(st.session_state.scheduler, date.today())

            if all_tasks:
                st.divider()
                st.markdown("#### Today's Tasks")
                if today_pairs:
                    sorted_pairs = sorted(today_pairs, key=lambda x: x[1].priority, reverse=True)
                    st.table([
                        {
                            "Pet": pet_name,
                            "Type": task.task_type.value,
                            "Description": task.description,
                            "Time": task.preferred_time.strftime("%H:%M") if task.preferred_time else "-",
                            "Duration (min)": task.duration,
                            "Priority": task.priority,
                            "Done": "Yes" if task.completed else "No",
                        }
                        for pet_name, task in sorted_pairs
                    ])
                else:
                    st.info("No tasks scheduled for today.")

                conflicts = st.session_state.scheduler.detect_conflicts()
                if conflicts:
                    st.warning("Scheduling conflicts detected — consider adjusting start times or durations:")
                    for conflict in conflicts:
                        st.error(conflict)

                pending = st.session_state.scheduler.filter_tasks(completed=False)
                done = st.session_state.scheduler.filter_tasks(completed=True)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Pending", len(pending))
                with col_b:
                    st.metric("Completed", len(done))

                st.divider()
                st.markdown("#### Generate Today's Plan")
                available_hours = st.number_input("Available hours today", min_value=1, max_value=24, value=8)

                if st.button("Generate plan"):
                    plan = st.session_state.scheduler.generate_plan(
                        target_date=date.today(),
                        available_hours=int(available_hours),
                    )
                    st.markdown(f"##### Plan for {plan.date}")
                    if plan.scheduled_tasks:
                        st.success(f"{len(plan.scheduled_tasks)} task(s) fit in your day.")
                        st.table([
                            {
                                "Priority": t.priority,
                                "Type": t.task_type.value,
                                "Description": t.description,
                                "Time": t.preferred_time.strftime("%H:%M") if t.preferred_time else "-",
                                "Duration (min)": t.duration,
                            }
                            for t in plan.scheduled_tasks
                        ])
                    else:
                        st.warning("No tasks could be scheduled — try increasing your available hours.")
                    st.info(plan.reasoning)

        # ---- This Week ----
        with week_tab:
            render_week_view(st.session_state.scheduler)

        # ---- This Month ----
        with month_tab:
            render_month_view(st.session_state.scheduler)


# ================================================================
# Care Plan Agent tab
# ================================================================
with tab_care:
    st.subheader("Care Plan Agent")
    st.caption(
        "Ask in plain language — plan your day, check for conflicts, or add a task. "
        "Anything you ask the agent to schedule will appear in the Schedule tab."
    )

    if not st.session_state.owner.pets:
        st.info("Add a pet in the sidebar first.")
    else:
        if st.session_state.care_agent is None:
            st.session_state.care_agent = CarePlanAgent(st.session_state.scheduler)

        pet_names = [p.name for p in st.session_state.owner.pets]

        for msg in st.session_state.care_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input: str | None = None

        if not st.session_state.care_messages:
            st.markdown("Not sure where to start? Try one of these:")
            sample_prompts = [
                f"Plan my day for {pet_names[0]}, I have 6 hours free",
                "Check for scheduling conflicts",
                f"Book a vet checkup for {pet_names[0]} next week",
            ]
            s_cols = st.columns(len(sample_prompts))
            for i, prompt in enumerate(sample_prompts):
                with s_cols[i]:
                    if st.button(prompt, key=f"care_sample_{i}", use_container_width=True):
                        user_input = prompt

        if typed := st.chat_input("", key="care_input"):
            user_input = typed

        if user_input:
            st.session_state.care_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        reply = st.session_state.care_agent.run(user_input)
                    except Exception as e:
                        reply = f"Sorry, something went wrong: {e}"
                st.markdown(reply)
            st.session_state.care_messages.append({"role": "assistant", "content": reply})


# ================================================================
# Health Advisor tab
# ================================================================
with tab_health:
    st.subheader("Health Advisor")
    st.caption(
        "A multi-turn conversation about your pet's wellbeing — medications, vet appointments, "
        "activity patterns, and more. Ask it to schedule anything and it will."
    )

    if not st.session_state.owner.pets:
        st.info("Add a pet in the sidebar first.")
    else:
        if st.session_state.health_agent is None:
            st.session_state.health_agent = HealthAdvisorAgent(st.session_state.scheduler)

        pet_names = [p.name for p in st.session_state.owner.pets]

        col_reset, _ = st.columns([1, 5])
        with col_reset:
            if st.button("Reset chat"):
                st.session_state.health_agent.reset_conversation()
                st.session_state.health_messages = []
                st.rerun()

        for msg in st.session_state.health_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input_h: str | None = None

        if not st.session_state.health_messages:
            st.markdown("Not sure where to start? Try one of these:")
            health_prompts = [
                f"Is {pet_names[0]}'s medication up to date?",
                f"When is {pet_names[0]}'s next vet appointment?",
                f"Schedule a flea treatment for {pet_names[0]}",
            ]
            h_cols = st.columns(len(health_prompts))
            for i, prompt in enumerate(health_prompts):
                with h_cols[i]:
                    if st.button(prompt, key=f"health_sample_{i}", use_container_width=True):
                        user_input_h = prompt

        if typed_h := st.chat_input("", key="health_input"):
            user_input_h = typed_h

        if user_input_h:
            st.session_state.health_messages.append({"role": "user", "content": user_input_h})
            with st.chat_message("user"):
                st.markdown(user_input_h)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        reply = st.session_state.health_agent.chat(user_input_h)
                    except Exception as e:
                        reply = f"Sorry, something went wrong: {e}"
                st.markdown(reply)
            st.session_state.health_messages.append({"role": "assistant", "content": reply})
