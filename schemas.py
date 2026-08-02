"""
Wolfie OS - Pydantic Guardrail Schemas
Ensures strict 1:1 type mapping from LLM outputs into native domain Enums.
"""

from pydantic import BaseModel, Field, field_validator
from datetime import time
from enum import Enum


class SpeciesEnum(str, Enum):
    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    REPTILE = "reptile"


class TaskPriorityEnum(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskFrequencyEnum(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class ExtractedTaskSchema(BaseModel):
    pet_name: str = Field(..., description="Name of the pet")
    title: str = Field(..., description="Short title of the task")
    species: SpeciesEnum = Field(..., description="Valid pet species enum")
    priority: TaskPriorityEnum = Field(
        ..., description="Single source of truth priority enum (high/medium/low)"
    )
    frequency: TaskFrequencyEnum = Field(
        ..., description="Recurrence frequency enum"
    )
    start_time_str: str = Field(
        ..., description="Task start time in HH:MM format (24-hour)"
    )
    duration_minutes: int = Field(
        default=15, description="Duration of the task in minutes"
    )

    @field_validator("start_time_str")
    def validate_time_format(cls, v: str) -> str:
        try:
            parts = v.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            time(hour, minute)
            return v
        except Exception:
            raise ValueError(f"Invalid time format '{v}'. Must be HH:MM in 24-hour format.")