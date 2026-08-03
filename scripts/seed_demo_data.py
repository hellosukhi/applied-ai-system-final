#!/usr/bin/env python3
"""Populate data/data.json with a realistic multi-pet demo household scenario."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pawpal_system import (
    FeedingTask,
    MedicationTask,
    Owner,
    Pet,
    SchedulerEngine,
    TaskPriority,
)


def main() -> None:
    engine = SchedulerEngine()
    owner = Owner(name="Jordan", daily_time_budget_minutes=120)

    wolfie = Pet(name="Wolfie", species="dog", age=4, health_flags=["pain"])
    cleo = Pet(name="Cleo", species="cat", age=2, health_flags=["sensitive"])

    wolfie.add_task(
        MedicationTask(
            task_id="seed-med-1",
            title="Otomax Ear Drops",
            duration_minutes=10,
            base_priority=8,
            priority=TaskPriority.HIGH,
            dosage="1 drop",
            dosage_window="morning",
            scheduled_time="08:00",
            frequency="daily",
            is_recurring=True,
            recurring_occurrences=2,
        )
    )
    wolfie.add_task(
        FeedingTask(
            task_id="seed-feed-1",
            title="Evening Walk",
            duration_minutes=20,
            base_priority=5,
            priority=TaskPriority.MEDIUM,
            food_type="walk",
            amount_grams=0,
            scheduled_time="18:00",
            frequency="daily",
        )
    )
    cleo.add_task(
        FeedingTask(
            task_id="seed-feed-2",
            title="Cat Feeding",
            duration_minutes=12,
            base_priority=4,
            priority=TaskPriority.MEDIUM,
            food_type="wet food",
            amount_grams=180,
            scheduled_time="18:30",
            frequency="daily",
        )
    )
    cleo.add_task(
        MedicationTask(
            task_id="seed-med-2",
            title="Medication",
            duration_minutes=8,
            base_priority=6,
            priority=TaskPriority.HIGH,
            dosage="1 tablet",
            dosage_window="evening",
            scheduled_time="20:00",
            frequency="daily",
        )
    )

    owner.add_pet(wolfie)
    owner.add_pet(cleo)

    output_path = Path("data/data.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    owner.save_to_json(str(output_path))

    serialized = engine.generate_global_plan(owner)
    print(f"Seeded demo data at {output_path} with {len(serialized)} scheduled plan items.")


if __name__ == "__main__":
    main()
