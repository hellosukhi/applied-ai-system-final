"""Wolfie OS — Streamlit presentation layer.

A persistent, tab-driven Command Hub over the deterministic core (pawpal_system)
and the agentic RAG layer (agent + schemas). Design contract:

* Launches into the Care Command Center (no step-lock wizard).
* Every state mutation / navigation calls st.rerun() so the UI is atomic on a
  single click (kills the double-click bug).
* Cards use native st.container(border=True) — never unclosed raw <div> wrappers,
  which Streamlit auto-closes and cannot use to wrap widgets.
* Deterministic domain logic stays in pawpal_system; this file only orchestrates.
"""

import os
import re
import uuid

import streamlit as st

from pawpal_system import (
    FeedingTask,
    MedicationTask,
    Owner,
    Pet,
    PetSpecies,
    SchedulerEngine,
    TaskPriority,
)
from agent import WolfieCareAgent

DATA_FILE = "data/data.json"

# Priority is the single source of truth; base_priority (urgency weight) is DERIVED
# from it, never entered as a competing raw number (fixes the legacy dual-input bug).
_BASE_PRIORITY_BY_LEVEL = {TaskPriority.HIGH: 8, TaskPriority.MEDIUM: 5, TaskPriority.LOW: 2}

st.set_page_config(
    page_title="Wolfie OS — Multi-Pet Care Sanctuary",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Master aesthetic. Three fonts, each with a job: Playfair Display (editorial
# headers), Plus Jakarta Sans (body/inputs), Inter (crisp UI accents — metrics,
# pills, buttons). High-specificity selectors are required so Streamlit's default
# Source Sans does not win the cascade on body text.
# --------------------------------------------------------------------------- #
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    .stApp { background-color: #FAFAFA !important; color: #1A1A1E !important; }

    /* Body / inputs -> Plus Jakarta Sans (specificity beats Streamlit's Source Sans). */
    html, body, .stApp, .stMarkdown, .stMarkdown p, p, li, label, span,
    div[data-testid="stMarkdownContainer"], .stTextInput input, .stTextArea textarea,
    .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Editorial headers -> Playfair Display. */
    h1, h2, h3, h4, [data-testid="stHeading"] {
        font-family: 'Playfair Display', Georgia, serif !important;
        font-weight: 600 !important;
        color: #1A1A1E !important;
        letter-spacing: -0.015em !important;
    }

    /* UI accents -> Inter. */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"],
    .stButton > button, .pill { font-family: 'Inter', sans-serif !important; }

    /* Native bordered containers -> porcelain cards. */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E5E8 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03) !important;
    }

    /* Remove the Streamlit top chrome that leaks the stray keyboard glyph in the header area. */
    [data-testid="stHeader"] {
        display: none !important;
    }

    /* Powder Sky Blue CTAs (#B0DEFF). */
    .stButton > button {
        background-color: #B0DEFF !important;
        color: #0F172A !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 9px 18px !important;
        transition: all 0.18s ease-in-out !important;
        box-shadow: 0 2px 10px rgba(176, 222, 255, 0.4) !important;
    }
    .stButton > button:hover {
        background-color: #93C5FD !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 14px rgba(176, 222, 255, 0.6) !important;
    }

    /* Pills (Inter) — forest RAG + priority variants. */
    .pill {
        display: inline-block; font-size: 0.78rem; font-weight: 600;
        padding: 3px 11px; border-radius: 20px; margin: 0 6px 6px 0;
    }
    .pill-forest { background: #F0F4F1; color: #39523A; border: 1px solid #D1E0D4; }
    .pill-high   { background: #FCE9EF; color: #941047; border: 1px solid #F2C9D8; }
    .pill-medium { background: #FFF6E6; color: #8A6516; border: 1px solid #F0DFBB; }
    .pill-low    { background: #F0F4F1; color: #39523A; border: 1px solid #D1E0D4; }

    /* Deep Berry conflict / guardrail card (#941047) — self-contained, no widget wrapping. */
    .conflict-alert-card {
        background-color: #FFF5F7 !important;
        border-left: 4px solid #941047 !important;
        border-radius: 8px !important;
        padding: 14px 16px !important;
        margin: 10px 0 !important;
        color: #941047 !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #F5F4F0 !important;
        border-right: 1px solid #E5E5E8 !important;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def clean_markdown_text(raw_text: str, max_len: int = 68) -> str:
    """Strip markdown noise (#, *, _, backticks) so RAG pills read as pristine prose."""
    text = re.sub(r"[#*_`>]", "", str(raw_text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")


def priority_pill(priority: TaskPriority) -> str:
    """Return a self-contained, color-coded priority pill span."""
    cls = {TaskPriority.HIGH: "pill-high", TaskPriority.MEDIUM: "pill-medium", TaskPriority.LOW: "pill-low"}[priority]
    return f'<span class="pill {cls}">{priority.value.upper()}</span>'


def go(tab: str) -> None:
    """Atomic navigation: set the active tab and force a single-click rerun."""
    st.session_state.active_tab = tab
    st.rerun()


def save() -> None:
    st.session_state.owner.save_to_json(DATA_FILE)


def _seed_demo_owner() -> Owner:
    """A ready-to-demo household that intentionally contains a schedule conflict."""
    owner = Owner(name="Sukhi Grewal", daily_time_budget_minutes=240)
    wolfie = Pet(name="Wolfie", species="dog", age=4, health_flags=["pain"])
    cleo = Pet(name="Cleo", species="cat", age=3)
    wolfie.add_task(MedicationTask(
        task_id="seed-otomax", title="Morning Otomax Ear Drops", duration_minutes=15,
        base_priority=8, priority=TaskPriority.HIGH, scheduled_time="08:00",
        frequency="daily", dosage="1 application", dosage_window="morning",
    ))
    cleo.add_task(FeedingTask(
        task_id="seed-feed", title="Cat Feeding & Separation", duration_minutes=15,
        base_priority=5, priority=TaskPriority.MEDIUM, scheduled_time="08:10",
        frequency="daily", food_type="wet food", amount_grams=120,
    ))
    owner.add_pet(wolfie)
    owner.add_pet(cleo)
    return owner


# --------------------------------------------------------------------------- #
# State hydration (load-once; seed a demo household on a fresh install)
# --------------------------------------------------------------------------- #
if "owner" not in st.session_state:
    if os.path.exists(DATA_FILE):
        loaded = Owner.load_from_json(DATA_FILE)
        st.session_state.owner = loaded if loaded.pets else _seed_demo_owner()
    else:
        st.session_state.owner = _seed_demo_owner()
    st.session_state.owner.save_to_json(DATA_FILE)

if "scheduler" not in st.session_state:
    st.session_state.scheduler = SchedulerEngine()
if "agent" not in st.session_state:
    st.session_state.agent = WolfieCareAgent()
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "Command Center"
st.session_state.setdefault("note_area", "")

owner = st.session_state.owner
scheduler = st.session_state.scheduler
agent = st.session_state.agent


def find_pet(name: str) -> Pet:
    return next(pet for pet in owner.pets if pet.name == name)


# --------------------------------------------------------------------------- #
# Sidebar — global navigation + household status
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🐾 Wolfie OS")
    st.caption("Multi-Pet Care Sanctuary · v1.0.0")
    st.markdown("---")
    st.markdown("#### Global Navigation")
    if st.button("🏠  Care Command Center", use_container_width=True):
        go("Command Center")
    if st.button("✨  Agentic Care Ingestion", use_container_width=True):
        go("Agent Ingestion")
    if st.button("⚙️  Companion & Household Setup", use_container_width=True):
        go("Household Setup")
    st.markdown("---")
    st.markdown("#### Household Status")
    st.write(f"**Owner:** {owner.name or '—'}")
    st.write(f"**Pets onboarded:** {len(owner.pets)}")
    st.write(f"**Daily budget:** {owner.daily_time_budget_minutes} min")


# --------------------------------------------------------------------------- #
# TAB 1 — Care Command Center (default landing)
# --------------------------------------------------------------------------- #
def render_command_center() -> None:
    st.markdown("# Care Command Center")
    st.caption("Live, deterministic schedule dashboard with real-time conflict detection.")

    if not owner.pets:
        with st.container(border=True):
            st.warning("⚠️ No companions onboarded yet.")
            if st.button("Go to Household Setup →"):
                go("Household Setup")
        return

    contextual = scheduler.expand_recurring_schedule_items(owner.get_all_tasks_contextual())
    conflicts = scheduler.detect_conflicts(contextual)
    total_tasks = sum(len(pet.tasks) for pet in owner.pets)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Companions", len(owner.pets))
    c2.metric("Scheduled Tasks", total_tasks)
    c3.metric("Daily Budget", f"{owner.daily_time_budget_minutes} min")
    c4.metric("Conflicts", len(conflicts), delta_color="inverse")

    if conflicts:
        rows = "".join(
            f"• <strong>{c['first'].task.title}</strong> ({c['first'].task.scheduled_time_label}) "
            f"overlaps <strong>{c['second'].task.title}</strong> ({c['second'].task.scheduled_time_label}) "
            f"— {c['reason']}<br/>"
            for c in conflicts
        )
        st.markdown(
            f'<div class="conflict-alert-card">🚨 <strong>Schedule Overlaps Detected</strong><br/>{rows}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("### ⚡ Optimized Daily Plan")
    plan = scheduler.generate_global_plan(owner)
    if plan:
        used = sum(item.task.duration_minutes for item in plan)
        st.caption(f"{len(plan)} tasks fit within budget · {used} of {owner.daily_time_budget_minutes} min used")
        for idx, item in enumerate(plan, start=1):
            task = item.task
            pill = priority_pill(TaskPriority.from_value(task.priority))
            st.markdown(
                f'<div style="padding:6px 0;">{idx}. <strong>{task.scheduled_time_label}</strong> — '
                f'{task.title} · <span style="color:#68707A;">{item.pet.name} · {task.duration_minutes} min</span> '
                f'{pill}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("No tasks fit the current time budget. Increase the budget in Setup, or add tasks.")

    st.markdown("### 🗓️ Active Schedule Board")
    for pet in owner.pets:
        with st.container(border=True):
            st.markdown(f"#### {pet.name} · {pet.species.value.capitalize()} · age {pet.age}")
            if not pet.tasks:
                st.caption("No care tasks assigned yet.")
                continue
            for task in scheduler.sort_by_time(pet.tasks):
                col_a, col_b, col_c = st.columns([3, 2, 1.2])
                col_a.write(f"**{task.title}**")
                col_b.write(f"🕒 {task.scheduled_time_label} · {task.duration_minutes} min")
                col_c.markdown(priority_pill(TaskPriority.from_value(task.priority)), unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# TAB 2 — Agentic Care Ingestion (AI parser + RAG)
# --------------------------------------------------------------------------- #
def render_agent_ingestion() -> None:
    if st.button("← Back to Command Center"):
        go("Command Center")
    st.markdown("# Agentic Care Ingestion")
    st.caption("Translate messy vet notes into validated, conflict-checkable domain tasks via RAG.")

    with st.container(border=True):
        st.markdown("#### Ingest an Unstructured Care Note")
        st.caption("One-click samples:")
        s1, s2 = st.columns(2)
        if s1.button("📋 Otomax Ear Drops (High Priority)"):
            st.session_state.note_area = "Wolfie needs Otomax ear drops daily at 08:00."
            st.rerun()
        if s2.button("🥩 Gabapentin with Food (20:00)"):
            st.session_state.note_area = "Wolfie needs Gabapentin with food at 20:00 daily."
            st.rerun()

        note_input = st.text_area(
            "Care note / instruction text", key="note_area", height=110,
            placeholder="e.g., Wolfie needs Otomax ear drops daily at 08:00…",
        )
        if st.button("✨ Parse & Synthesize Task"):
            if not note_input.strip():
                st.session_state.parse_error = "Please enter a note to parse."
                st.session_state.pop("last_parsed", None)
            else:
                try:
                    st.session_state.last_parsed = agent.plan_care_task(note_input)
                    st.session_state.parse_error = None
                except Exception as exc:  # guardrail rejection surfaces here, no state mutation
                    st.session_state.parse_error = str(exc)
                    st.session_state.pop("last_parsed", None)
            st.rerun()

    if st.session_state.get("parse_error"):
        st.markdown(
            f'<div class="conflict-alert-card">🛡️ <strong>Guardrail rejected this note.</strong><br/>'
            f'{st.session_state.parse_error}</div>',
            unsafe_allow_html=True,
        )
        return

    parsed = st.session_state.get("last_parsed")
    if not parsed:
        return

    schema = parsed["task_schema"]
    trace = parsed["reasoning_trace"]
    with st.container(border=True):
        st.markdown("#### Validated Task Result")
        f1, f2, f3 = st.columns(3)
        f1.metric("Pet", schema.pet_name)
        f2.metric("Priority", schema.priority.value.upper())
        f3.metric("Start", schema.start_time_str)
        st.write(f"**Title:** {schema.title}  ·  **Species:** {schema.species.value}  ·  **Duration:** {schema.duration_minutes} min")

        st.markdown("**🌿 Retrieved veterinary context (RAG):**")
        pills = "".join(
            f'<span class="pill pill-forest">🌿 {clean_markdown_text(chunk)}</span>'
            for chunk in trace["retrieved_rag_context"]
        )
        st.markdown(pills, unsafe_allow_html=True)
        if trace["rag_applied"]:
            applied = "".join(
                f'<span class="pill pill-forest">✅ {clean_markdown_text(rule)}</span>'
                for rule in trace["rag_applied"]
            )
            st.markdown(applied, unsafe_allow_html=True)

        if owner.pets:
            st.markdown("---")
            target = st.selectbox("Assign to companion", [pet.name for pet in owner.pets], key="commit_target")
            if st.button("➕ Commit Validated Task to Schedule"):
                find_pet(target).add_task(schema.to_domain_task())
                save()
                st.session_state.pop("last_parsed", None)
                go("Command Center")
        else:
            st.info("Add a companion in Household Setup before committing tasks.")


# --------------------------------------------------------------------------- #
# TAB 3 — Companion & Household Setup
# --------------------------------------------------------------------------- #
def render_household_setup() -> None:
    if st.button("← Back to Command Center"):
        go("Command Center")
    st.markdown("# Companion & Household Setup")
    st.caption("Owner details, daily time budget, and companion profiles.")

    with st.container(border=True):
        st.markdown("#### System Operational Status & Checklist")
        r1, r2, r3 = st.columns(3)
        owner_ok = bool(owner.name.strip())
        pets_ok = len(owner.pets) > 0
        budget_ok = owner.daily_time_budget_minutes > 0
        r1.markdown(f"**Owner Name**  \n{'✅ Set' if owner_ok else '❌ Required'}")
        r2.markdown(f"**Pet Profiles**  \n{'✅ ' + str(len(owner.pets)) + ' onboarded' if pets_ok else '❌ Add one'}")
        r3.markdown(f"**Time Budget**  \n{'✅ ' + str(owner.daily_time_budget_minutes) + ' min' if budget_ok else '❌ Set > 0'}")

    with st.container(border=True):
        st.markdown("#### Owner Profile & Daily Budget")
        new_name = st.text_input("Owner name", value=owner.name, placeholder="e.g., Sukhi")
        new_budget = st.number_input("Daily care-time budget (minutes)", min_value=0, max_value=480,
                                     value=owner.daily_time_budget_minutes, step=15)
        if st.button("Save Owner Profile"):
            owner.name = new_name.strip()
            owner.update_time_budget(int(new_budget))
            save()
            st.rerun()

    with st.container(border=True):
        st.markdown("#### Add a Companion")
        with st.form("add_pet_form"):
            p_name = st.text_input("Pet name", placeholder="e.g., Wolfie")
            p_species = st.selectbox("Species", [s.value for s in PetSpecies])
            p_age = st.number_input("Age (years)", min_value=0, max_value=30, value=2)
            if st.form_submit_button("Add Companion"):
                if not p_name.strip():
                    st.warning("Pet name is required.")
                else:
                    owner.add_pet(Pet(name=p_name.strip(), species=p_species, age=int(p_age)))
                    save()
                    st.rerun()

    if owner.pets:
        with st.container(border=True):
            st.markdown("#### Add a Care Task")
            pet_name = st.selectbox("Companion", [pet.name for pet in owner.pets], key="task_pet")
            ttype = st.selectbox("Task type", ["feeding", "medication"], key="task_type")
            title = st.text_input("Task title", placeholder="e.g., Breakfast", key="task_title")
            # Priority is the ONLY urgency input; base_priority is derived (single source of truth).
            level = st.selectbox("Priority", [p.value for p in TaskPriority], index=1, key="task_priority")
            when = st.text_input("Scheduled time (HH:MM, optional)", placeholder="e.g., 08:00", key="task_time")
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=10, key="task_dur")
            if st.button("Save Care Task"):
                priority = TaskPriority.from_value(level)
                common = dict(
                    task_id=uuid.uuid4().hex, title=title.strip() or ttype.capitalize(),
                    duration_minutes=int(duration), base_priority=_BASE_PRIORITY_BY_LEVEL[priority],
                    priority=priority, scheduled_time=when.strip() or None,
                )
                try:
                    task = (MedicationTask(**common, dosage="", dosage_window="")
                            if ttype == "medication" else FeedingTask(**common, food_type="", amount_grams=0))
                    find_pet(pet_name).add_task(task)
                    save()
                    st.success(f"Added '{task.title}' to {pet_name}.")
                    st.rerun()
                except ValueError as exc:
                    st.warning(f"Could not add task: {exc}")


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
_TABS = {
    "Command Center": render_command_center,
    "Agent Ingestion": render_agent_ingestion,
    "Household Setup": render_household_setup,
}
_TABS.get(st.session_state.active_tab, render_command_center)()
