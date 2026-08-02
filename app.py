import os
import uuid

import streamlit as st

from pawpal_system import FeedingTask, MedicationTask, Owner, Pet, SchedulerEngine, TaskPriority

DATA_FILE = "data.json"


def render_priority_status(task) -> None:
    """Render a task's priority using a high-visibility Streamlit status component.

    HIGH -> st.error (red), MEDIUM -> st.warning (amber), LOW -> st.info (blue).
    """
    priority = TaskPriority.from_value(task.priority)
    label = priority.value.upper()
    if priority == TaskPriority.HIGH:
        st.error(f"🔴 Priority: {label} — needs attention first")
    elif priority == TaskPriority.MEDIUM:
        st.warning(f"🟠 Priority: {label} — schedule when convenient")
    else:
        st.info(f"🔵 Priority: {label} — flexible timing")

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

st.title("🐾 PawPal+")

st.markdown(
    """
This view now uses the backend classes from the logic layer so your UI creates real
owner, pet, and task objects that persist during the session.
"""
)

# Streamlit re-executes this whole script top-to-bottom on every interaction, so all
# durable state lives in st.session_state. The domain objects are hydrated from disk
# exactly once (guarded by the "not in session_state" check) and then survive reruns
# in memory; each mutating action below re-persists via save_to_json. This is the
# load-once / save-on-mutation half of the stateless-persistence contract owned by
# pawpal_system's to_dict/from_dict pipeline.
if "owner" not in st.session_state:
    if os.path.exists(DATA_FILE):
        st.session_state.owner = Owner.load_from_json(DATA_FILE)
    else:
        st.session_state.owner = Owner(name="Jordan", daily_time_budget_minutes=60)

if "scheduler" not in st.session_state:
    # The engine is stateless, but caching it avoids reallocating it on every rerun.
    st.session_state.scheduler = SchedulerEngine()

owner = st.session_state.owner
scheduler = st.session_state.scheduler

st.sidebar.header("Owner profile")
owner.name = st.sidebar.text_input("Owner name", value=owner.name, key="owner_name_input")
owner.update_time_budget(
    int(
        st.sidebar.number_input(
            "Daily time budget (minutes)",
            min_value=0,
            max_value=480,
            value=owner.daily_time_budget_minutes,
            key="budget_input",
        )
    )
)
owner.save_to_json(DATA_FILE)

st.subheader("Add a pet")
with st.expander("Create a pet profile", expanded=True):
    pet_name = st.text_input("Pet name", value="Mochi", key="pet_name_input")
    species = st.selectbox("Species", ["dog", "cat", "other"], key="pet_species_input")
    age = st.number_input("Age", min_value=0, max_value=30, value=3, key="pet_age_input")

    if st.button("Add pet", key="add_pet_button"):
        new_pet = Pet(name=pet_name.strip() or "Unnamed pet", species=species, age=int(age))
        owner.add_pet(new_pet)
        st.session_state.owner = owner
        owner.save_to_json(DATA_FILE)
        st.success(f"Added {new_pet.name} to {owner.name}'s care plan.")

st.divider()

st.subheader("Your pets")
if owner.pets:
    for pet in owner.pets:
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"🐾 **{pet.name}** ({pet.species.value}, age {pet.age})")
            with col2:
                if pet.health_flags:
                    health_badge = ", ".join(pet.health_flags)
                    st.caption(f"Health: {health_badge}")
            
            if pet.tasks:
                # Display tasks in a compact table format
                pet_tasks_data = []
                for task in pet.tasks:
                    task_type = "💊 Medication" if task.__class__.__name__ == "MedicationTask" else "🍽️ Feeding"
                    pet_tasks_data.append({
                        "Type": task_type,
                        "Task": task.title,
                        "Duration": f"{task.duration_minutes} min",
                        "Priority": task.priority.value.upper(),
                        "Status": "✓ Done" if task.is_completed else "○ Pending",
                    })
                st.table(pet_tasks_data)
            else:
                st.caption("  • No tasks yet")
else:
    st.info("No pets yet. Add one above to start building a plan.")

st.divider()

st.subheader("Add a task")
if owner.pets:
    selected_pet_name = st.selectbox(
        "Choose a pet",
        [pet.name for pet in owner.pets],
        key="task_pet_select",
    )
    selected_pet = next(pet for pet in owner.pets if pet.name == selected_pet_name)

    task_type = st.selectbox("Task type", ["feeding", "medication"], key="task_type_select")
    task_title = st.text_input("Task title", value="Meal time", key="task_title_input")
    priority_level = st.selectbox(
        "Priority",
        [TaskPriority.LOW.value, TaskPriority.MEDIUM.value, TaskPriority.HIGH.value],
        index=1,
        key="task_priority_select",
    )
    duration = st.number_input(
        "Duration (minutes)", min_value=1, max_value=240, value=10, key="task_duration_input"
    )
    base_priority = st.number_input(
        "Base priority",
        min_value=0,
        max_value=10,
        value=5,
        key="task_base_priority_input",
    )

    if task_type == "feeding":
        food_type = st.text_input("Food type", value="dry food", key="food_type_input")
        amount_grams = st.number_input(
            "Amount (grams)", min_value=1, max_value=1000, value=200, key="amount_input"
        )
        if st.button("Add task", key="add_feeding_task_button"):
            task = FeedingTask(
                task_id=uuid.uuid4().hex,
                title=task_title.strip() or "Feeding",
                duration_minutes=int(duration),
                base_priority=int(base_priority),
                priority=priority_level,
                food_type=food_type,
                amount_grams=int(amount_grams),
            )
            selected_pet.add_task(task)
            st.session_state.owner = owner
            owner.save_to_json(DATA_FILE)
            st.success(f"Added {task.title} for {selected_pet.name}.")
    else:
        dosage = st.text_input("Dosage", value="1 tablet", key="dosage_input")
        dosage_window = st.text_input("Window", value="morning", key="dosage_window_input")
        if st.button("Add task", key="add_medication_task_button"):
            task = MedicationTask(
                task_id=uuid.uuid4().hex,
                title=task_title.strip() or "Medication",
                duration_minutes=int(duration),
                base_priority=int(base_priority),
                priority=priority_level,
                dosage=dosage,
                dosage_window=dosage_window,
            )
            selected_pet.add_task(task)
            st.session_state.owner = owner
            owner.save_to_json(DATA_FILE)
            st.success(f"Added {task.title} for {selected_pet.name}.")
else:
    st.info("Add a pet first so you can attach tasks to it.")

st.divider()

st.subheader("🗓️ Live Optimized Care Schedule")

if st.button("⚡ Generate Optimal Daily Schedule", key="generate_schedule_button"):
    if not owner.pets or not any(pet.tasks for pet in owner.pets):
        st.info("Add at least one pet and one task before generating a schedule.")
    else:
        # Step 1: Expand recurring tasks and collect all contextual items
        all_contextual_items = scheduler.expand_recurring_schedule_items(owner.get_all_tasks_contextual())
        
        # Step 2: Run conflict scanner with verified parameter type
        active_warnings = scheduler.detect_conflicts(all_contextual_items)
        
        # Step 3: Render conflicts prominently at top if any exist
        if active_warnings:
            st.warning("⚠️ Scheduling Conflicts Detected!")
            for conflict_dict in active_warnings:
                first_item = conflict_dict["first"]
                second_item = conflict_dict["second"]
                reason = conflict_dict["reason"]
                st.error(
                    f"**{first_item.pet.name}** — {first_item.task.title} at {first_item.task.scheduled_time_label} "
                    f"and **{second_item.pet.name}** — {second_item.task.title} at {second_item.task.scheduled_time_label} "
                    f"have a {reason}. Please adjust times to resolve."
                )
            st.divider()
        
        # Step 4: Generate optimal budget-constrained plan
        optimized_items = scheduler.generate_global_plan(owner)
        
        if not optimized_items:
            st.info("No tasks could be scheduled within the remaining time budget allocation.")
        else:
            # Display metrics dashboard
            total_selected_time = sum(item.task.duration_minutes for item in optimized_items)
            remaining_time = owner.daily_time_budget_minutes - total_selected_time
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Daily Time Budget", f"{owner.daily_time_budget_minutes} min")
            with col2:
                st.metric("Tasks Selected", f"{len(optimized_items)} tasks", delta=f"{total_selected_time} min used")
            with col3:
                st.metric("Time Remaining", f"{remaining_time} min", delta_color="off")
            
            scheduled_tasks = [item.task for item in optimized_items if item.task.scheduled_time_value is not None]
            next_slot = scheduler.find_next_available_slot(scheduled_tasks, duration_minutes=15)
            if next_slot is not None:
                st.caption(f"🕒 Suggested next open slot: {next_slot.strftime('%H:%M')} for a 15-minute task")

            st.divider()
            st.success("✓ Schedule generated successfully!")
            st.subheader("Your Optimized Care Plan")
            
            # Step 5: Render each scheduled item with clean formatting and task-specific details
            for idx, item in enumerate(optimized_items, start=1):
                with st.container():
                    task = item.task
                    pet = item.pet
                    
                    # Clean native formatting
                    time_label = task.scheduled_time_label
                    
                    # Render card header with hierarchical structure
                    st.markdown(f"### {idx}. **{time_label}** — {task.title} for **{pet.name}**")
                    st.caption(f"Species: {pet.species.value} | Duration: {task.duration_minutes} min | Priority: {task.base_priority}/10")

                    # Map the explicit TaskPriority enum to a color-coded status banner.
                    render_priority_status(task)

                    # Subtype-specific detail is discovered by attribute presence
                    # (duck typing) rather than isinstance branching, so adding a new
                    # Task subclass with its own fields needs no change here — the view
                    # renders whatever care attributes a task happens to expose.
                    instructions_parts = []

                    # Check for Medication task attributes
                    if hasattr(task, "dosage") and task.dosage:
                        instructions_parts.append(f"💊 Dosage: {task.dosage}")
                    if hasattr(task, "dosage_window") and task.dosage_window:
                        instructions_parts.append(f"⏰ Window: {task.dosage_window}")
                    
                    # Check for Feeding task attributes
                    if hasattr(task, "food_type") and task.food_type:
                        instructions_parts.append(f"🍽️ Food: {task.food_type}")
                    if hasattr(task, "amount_grams") and task.amount_grams:
                        instructions_parts.append(f"⚖️ Amount: {task.amount_grams}g")
                    
                    # Display instructions if any were found
                    if instructions_parts:
                        care_instruction = " | ".join(instructions_parts)
                        st.success(f"📋 {care_instruction}")
                    
                    st.divider()
