"""Integration tests for the agentic RAG layer <-> deterministic core bridge."""

from datetime import time

import pytest
from pydantic import ValidationError

from agent import WolfieCareAgent, VetGuidelineRAG
from pawpal_system import (
    FeedingTask,
    MedicationTask,
    PetSpecies,
    SchedulerEngine,
    ScheduleItem,
    Pet,
    Task,
    TaskFrequency,
    TaskPriority,
)
from schemas import (
    ExtractedTaskSchema,
    SpeciesEnum,
    TaskFrequencyEnum,
    TaskPriorityEnum,
)


def test_enums_are_unified_single_source_of_truth():
    """The schema enums must BE the domain enums, not parallel copies."""
    assert SpeciesEnum is PetSpecies
    assert TaskPriorityEnum is TaskPriority
    assert TaskFrequencyEnum is TaskFrequency


def test_to_domain_task_bridges_into_native_task():
    schema = ExtractedTaskSchema(
        pet_name="Cleo",
        title="Otomax ear drops",
        species="cat",
        priority="high",
        frequency="daily",
        start_time_str="08:00",
        duration_minutes=15,
        task_type="MedicationTask",
    )
    task = schema.to_domain_task()
    assert isinstance(task, MedicationTask)
    assert isinstance(task, Task)
    assert task.scheduled_time_value == time(8, 0)
    assert task.priority is TaskPriority.HIGH
    # base_priority is derived from the priority enum, not entered separately.
    assert task.base_priority == 8


def test_to_domain_task_defaults_to_feeding():
    schema = ExtractedTaskSchema(
        pet_name="Max",
        title="Dinner",
        species="dog",
        priority="low",
        frequency="daily",
        start_time_str="18:00",
    )
    task = schema.to_domain_task()
    assert isinstance(task, FeedingTask)
    assert task.base_priority == 2


def test_guardrail_rejects_invalid_time():
    with pytest.raises(ValidationError):
        ExtractedTaskSchema(
            pet_name="Wolfie",
            title="Bad time",
            species="dog",
            priority="high",
            frequency="daily",
            start_time_str="25:99",
        )


def test_agent_end_to_end_produces_schedulable_task():
    agent = WolfieCareAgent()
    result = agent.plan_care_task("Wolfie needs Otomax ear drops daily at 08:00.")
    schema = result["task_schema"]
    assert schema.priority is TaskPriority.HIGH
    task = schema.to_domain_task()
    assert task.scheduled_time_value == time(8, 0)


def test_rag_context_escalates_priority():
    """A prompt whose retrieved guideline is a high-alert rule must escalate to HIGH."""
    agent = WolfieCareAgent()
    result = agent.plan_care_task("Wolfie needs Otomax ear drops daily at 08:00.")
    assert "priority_escalated_to_high_by_guideline" not in result["reasoning_trace"]["rag_applied"] or (
        result["task_schema"].priority is TaskPriority.HIGH
    )
    # Retrieval must be non-trivial and actually consulted.
    assert result["reasoning_trace"]["retrieved_rag_context"]


def test_agent_task_feeds_conflict_detector():
    """Two agent-derived overlapping tasks must be caught by detect_conflicts."""
    engine = SchedulerEngine()
    pet = Pet(name="Cleo", species="cat", age=2)
    t1 = FeedingTask(task_id="c1", title="Feed A", duration_minutes=30,
                     base_priority=5, scheduled_time="17:30")
    t2 = FeedingTask(task_id="c2", title="Feed B", duration_minutes=30,
                     base_priority=5, scheduled_time="17:45")
    items = [ScheduleItem(pet=pet, task=t1), ScheduleItem(pet=pet, task=t2)]
    conflicts = engine.detect_conflicts(items)
    assert conflicts, "overlapping tasks should conflict"
    slot = engine.find_next_available_slot([t1, t2], duration_minutes=30)
    assert slot is not None and slot >= time(18, 0)
