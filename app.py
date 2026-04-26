from datetime import date, time

import streamlit as st

from agents import CarePlanAgent, HealthAdvisorAgent
from pawpal_system import Frequency, Owner, Pet, Scheduler, Task, TaskType

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

# --- Initialize session state ---
if "owner" not in st.session_state:
    st.session_state.owner = None
if "scheduler" not in st.session_state:
    st.session_state.scheduler = None
if "care_agent" not in st.session_state:
    st.session_state.care_agent = None
if "health_agent" not in st.session_state:
    st.session_state.health_agent = None
if "care_messages" not in st.session_state:
    st.session_state.care_messages = []
if "health_messages" not in st.session_state:
    st.session_state.health_messages = []

# --- Owner setup (outside tabs so st.stop() guard works for all tabs) ---
st.subheader("Owner Setup")
owner_name = st.text_input("Owner name", value="Jordan")

if st.button("Create owner"):
    st.session_state.owner = Owner(name=owner_name)
    st.session_state.scheduler = Scheduler(owner=st.session_state.owner)
    st.session_state.care_agent = CarePlanAgent(st.session_state.scheduler)
    st.session_state.health_agent = HealthAdvisorAgent(st.session_state.scheduler)
    st.session_state.care_messages = []
    st.session_state.health_messages = []
    st.success(f"Welcome, {owner_name}! Your profile has been created.")

if st.session_state.owner is None:
    st.info("Enter your name above and click 'Create owner' to get started.")
    st.stop()

st.divider()

# --- Tabs ---
tab_schedule, tab_care_agent, tab_health_agent = st.tabs([
    "Schedule", "Care Plan Agent", "Health Advisor"
])

# ================================================================
# Schedule tab
# ================================================================
with tab_schedule:
    # --- Pet setup ---
    st.subheader("Your Pets")
    pet_name = st.text_input("Pet name", value="Mochi")
    pet_breed = st.text_input("Breed", value="Shiba Inu")
    pet_age = st.number_input("Age", min_value=0, max_value=30, value=2)

    if st.button("Add pet"):
        try:
            pet = Pet(name=pet_name, breed=pet_breed, age=int(pet_age))
            st.session_state.owner.add_pet(pet)
            # Recreate agents so their system prompts reflect the updated pet list
            st.session_state.care_agent = CarePlanAgent(st.session_state.scheduler)
            st.session_state.health_agent = HealthAdvisorAgent(st.session_state.scheduler)
            st.success(f"{pet_name} has been added to your care list.")
        except ValueError as e:
            st.error(str(e))

    if st.session_state.owner.pets:
        st.table([
            {"Name": p.name, "Breed": p.breed, "Age": p.age}
            for p in st.session_state.owner.pets
        ])

    st.divider()

    # --- Task setup ---
    st.subheader("Add a Task")

    if not st.session_state.owner.pets:
        st.warning("Add at least one pet before adding tasks.")
    else:
        pet_names = [p.name for p in st.session_state.owner.pets]
        selected_pet_name = st.selectbox("Assign to pet", pet_names)

        col1, col2, col3 = st.columns(3)
        with col1:
            task_title = st.text_input("Task description", value="Morning walk")
        with col2:
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
        with col3:
            priority = st.selectbox("Priority (1=low, 5=high)", [1, 2, 3, 4, 5], index=2)

        col4, col5 = st.columns(2)
        with col4:
            task_type = st.selectbox("Task type", [t.value for t in TaskType])
        with col5:
            preferred_hour = st.number_input(
                "Preferred start time (hour, 0–23)", min_value=0, max_value=23, value=8
            )

        if st.button("Add task"):
            try:
                target_pet = next(
                    p for p in st.session_state.owner.pets if p.name == selected_pet_name
                )
                task = Task(
                    task_type=TaskType(task_type),
                    description=task_title,
                    duration=int(duration),
                    priority=priority,
                    frequency=Frequency.DAILY,
                    preferred_time=time(int(preferred_hour), 0),
                )
                st.session_state.scheduler.add_task(target_pet, task)
                st.success(f"'{task_title}' added to {selected_pet_name}'s schedule.")
            except ValueError as e:
                st.error(str(e))

    # --- Current tasks table (sorted by priority) ---
    all_tasks = st.session_state.owner.get_all_tasks()
    if all_tasks:
        st.markdown("**Current tasks (sorted by priority):**")
        sorted_tasks = sorted(all_tasks, key=lambda t: t.priority, reverse=True)
        st.table([
            {
                "Pet": next(
                    p.name for p in st.session_state.owner.pets if task in p.tasks
                ),
                "Type": task.task_type.value,
                "Description": task.description,
                "Time": task.preferred_time.strftime("%H:%M") if task.preferred_time else "—",
                "Duration (min)": task.duration,
                "Priority": task.priority,
                "Done": "Yes" if task.completed else "No",
            }
            for task in sorted_tasks
        ])

    # --- Conflict warnings ---
    if all_tasks:
        conflicts = st.session_state.scheduler.detect_conflicts()
        if conflicts:
            st.warning(
                "**Scheduling conflicts detected.** "
                "The tasks below overlap in time — consider adjusting their start times or durations:"
            )
            for conflict in conflicts:
                st.error(conflict)

    # --- Pending vs completed breakdown ---
    if all_tasks:
        pending = st.session_state.scheduler.filter_tasks(completed=False)
        done = st.session_state.scheduler.filter_tasks(completed=True)
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Pending tasks", len(pending))
        with col_b:
            st.metric("Completed tasks", len(done))

    st.divider()

    # --- Generate schedule ---
    st.subheader("Generate Today's Schedule")
    available_hours = st.number_input(
        "Your available hours today", min_value=1, max_value=24, value=8
    )

    if st.button("Generate schedule"):
        plan = st.session_state.scheduler.generate_plan(
            target_date=date.today(),
            available_hours=int(available_hours),
        )
        st.markdown(f"### Daily Plan for {plan.date}")
        if plan.scheduled_tasks:
            st.success(f"{len(plan.scheduled_tasks)} task(s) scheduled.")
            st.table([
                {
                    "Priority": t.priority,
                    "Type": t.task_type.value,
                    "Description": t.description,
                    "Time": t.preferred_time.strftime("%H:%M") if t.preferred_time else "—",
                    "Duration (min)": t.duration,
                }
                for t in plan.scheduled_tasks
            ])
        else:
            st.warning(
                "No tasks could be scheduled. "
                "Try adding tasks or increasing your available hours."
            )
        st.info(plan.reasoning)


# ================================================================
# Care Plan Agent tab
# ================================================================
with tab_care_agent:
    st.subheader("Care Plan Agent")
    st.caption("Ask Claude to plan your day in plain language.")

    if st.session_state.care_agent is None:
        st.session_state.care_agent = CarePlanAgent(st.session_state.scheduler)

    for msg in st.session_state.care_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input(
        "e.g. Plan my day for Luna, I have 4 hours", key="care_input"
    ):
        st.session_state.care_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Planning..."):
                try:
                    reply = st.session_state.care_agent.run(prompt)
                except Exception as e:
                    reply = f"Sorry, something went wrong: {e}"
            st.markdown(reply)
        st.session_state.care_messages.append({"role": "assistant", "content": reply})


# ================================================================
# Health Advisor tab
# ================================================================
with tab_health_agent:
    st.subheader("Health Advisor")
    st.caption("Multi-turn conversation about your pet's health.")

    if st.session_state.health_agent is None:
        st.session_state.health_agent = HealthAdvisorAgent(st.session_state.scheduler)

    col_reset, _ = st.columns([1, 4])
    with col_reset:
        if st.button("Reset conversation"):
            st.session_state.health_agent.reset_conversation()
            st.session_state.health_messages = []
            st.rerun()

    for msg in st.session_state.health_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input(
        "Ask about your pet's health...", key="health_input"
    ):
        st.session_state.health_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                try:
                    reply = st.session_state.health_agent.chat(prompt)
                except Exception as e:
                    reply = f"Sorry, something went wrong: {e}"
            st.markdown(reply)
        st.session_state.health_messages.append({"role": "assistant", "content": reply})
