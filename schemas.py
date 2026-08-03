"""
Wolfie OS - Pydantic Guardrail Schemas & Agentic Domain Bridge

Single source of truth: the agent layer speaks the SAME typed vocabulary as the
deterministic core. Rather than redefining parallel enums (which silently diverged
from ``pawpal_system`` and broke round-tripping), we re-export the domain enums so
an agent-produced task is constructor-compatible with the scheduler by definition.

``ExtractedTaskSchema`` is the guardrail boundary: raw agent/LLM output is coerced
into these types or rejected loudly, then ``to_domain_task()`` materializes a native
``Task`` subclass the deterministic engine can schedule and conflict-check directly.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

# The one-way import (schemas -> pawpal_system, never the reverse) keeps the graph
# acyclic and makes the domain layer the authoritative owner of the vocabulary.
from pawpal_system import (
    FeedingTask,
    MedicationTask,
    PetSpecies,
    Task,
    TaskFrequency,
    TaskPriority,
)

# Backward-compatible aliases. The isolated ``*Enum`` names defined here previously are
# now deprecated pointers to the domain enums, so existing imports keep resolving while
# the definitions live in exactly one place.
SpeciesEnum = PetSpecies
TaskPriorityEnum = TaskPriority
TaskFrequencyEnum = TaskFrequency

# Priority is the single source of truth; the numeric ``base_priority`` the urgency
# math consumes is DERIVED from it here, never entered as a competing raw input.
_BASE_PRIORITY_BY_LEVEL = {
    TaskPriority.HIGH: 8,
    TaskPriority.MEDIUM: 5,
    TaskPriority.LOW: 2,
}

_SUPPORTED_TASK_TYPES = {"FeedingTask", "MedicationTask"}


class ExtractedTaskSchema(BaseModel):
    """Validated envelope for a single care task extracted from unstructured text."""

    pet_name: str = Field(..., description="Name of the pet")
    title: str = Field(..., description="Short title of the task")
    species: PetSpecies = Field(..., description="Valid pet species enum")
    priority: TaskPriority = Field(
        ..., description="Single source of truth priority enum (high/medium/low)"
    )
    frequency: TaskFrequency = Field(..., description="Recurrence frequency enum")
    start_time_str: str = Field(
        ..., description="Task start time in HH:MM format (24-hour)"
    )
    duration_minutes: int = Field(
        default=15, ge=1, description="Duration of the task in minutes"
    )
    task_type: str = Field(
        default="FeedingTask",
        description="Concrete domain subclass: FeedingTask or MedicationTask",
    )

    @field_validator("species", mode="before")
    @classmethod
    def _coerce_species(cls, value: object) -> PetSpecies:
        return PetSpecies.from_value(value)

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, value: object) -> TaskPriority:
        return TaskPriority.from_value(value)

    @field_validator("frequency", mode="before")
    @classmethod
    def _coerce_frequency(cls, value: object) -> TaskFrequency:
        return TaskFrequency.from_value(value)

    @field_validator("start_time_str")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Reject any string that is not a real 24-hour HH:MM clock time."""
        # This is the guardrail that stops a hallucinated "25:99" from ever reaching
        # the scheduler: we round-trip it through datetime.time, whose constructor
        # enforces 0-23 / 0-59, and surface a ValidationError on failure.
        from datetime import time

        try:
            hour_text, minute_text = v.split(":")
            time(int(hour_text), int(minute_text))
        except Exception as exc:
            raise ValueError(
                f"Invalid time format '{v}'. Must be HH:MM in 24-hour format."
            ) from exc
        return v

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        if v not in _SUPPORTED_TASK_TYPES:
            raise ValueError(
                f"Unsupported task_type '{v}'. Expected one of {sorted(_SUPPORTED_TASK_TYPES)}."
            )
        return v

    def to_domain_task(self, task_id: Optional[str] = None) -> Task:
        """Materialize this validated payload into a native domain ``Task`` subclass.

        The bridge the audit flagged as missing: it hands the deterministic engine a
        real ``FeedingTask`` / ``MedicationTask`` — already conflict-checkable and
        serializable — with ``base_priority`` derived from the priority enum so the
        urgency math has no competing numeric input.
        """
        resolved_id = task_id or f"agent-{self.pet_name.lower()}-{self.start_time_str.replace(':', '')}"
        common_kwargs = {
            "task_id": resolved_id,
            "title": self.title,
            "duration_minutes": self.duration_minutes,
            "base_priority": _BASE_PRIORITY_BY_LEVEL[self.priority],
            "pet_name": self.pet_name,
            "priority": self.priority,
            "scheduled_time": self.start_time_str,
            "frequency": self.frequency,
        }
        if self.task_type == "MedicationTask":
            return MedicationTask(**common_kwargs)
        return FeedingTask(**common_kwargs)
