from datetime import date, time, timedelta

import pytest

from pawpal_system import (
    FeedingTask,
    MedicationTask,
    Owner,
    Pet,
    PetSpecies,
    ScheduleAgentResponse,
    ScheduleItem,
    Scheduler,
    SchedulerEngine,
    Task,
    TaskFrequency,
    TaskPriority,
    parse_ai_schedule_response,
)
from agent import WolfieCareAgent


def test_task_completion():
    """Verify that calling mark_complete() mutates the task state to True."""
    # 1. Arrange
    task = FeedingTask(
        task_id="t-comp-1",
        title="Morning Kibble",
        duration_minutes=15,
        base_priority=5,
        food_type="dry food",
        amount_grams=150,
        scheduled_time="08:00",
    )

    # 2. Act
    assert task.is_completed is False, "Task should initialize as uncompleted."
    result = task.mark_complete()

    # 3. Assert
    assert task.is_completed is True, "Calling mark_complete() must set is_completed to True."
    assert result is None, "Non-recurring tasks should not create a new occurrence."


def test_mark_complete_creates_next_daily_occurrence():
    task = FeedingTask(
        task_id="feed-11",
        title="Daily brushing",
        duration_minutes=10,
        base_priority=3,
        food_type="dry food",
        amount_grams=150,
        scheduled_time="08:00",
        is_recurring=True,
        frequency="daily",
    )

    next_task = task.mark_complete()

    assert task.is_completed is True
    assert next_task is not None
    assert next_task.task_id == "feed-11-next"
    assert next_task.is_completed is False
    assert next_task.frequency is TaskFrequency.DAILY
    assert next_task.scheduled_time == "08:00"
    assert next_task.due_date == date.today() + timedelta(days=1)


def test_task_addition_increments_count():
    """Verify that appending a task to a Pet increases its internal itinerary collection count."""
    # 1. Arrange
    pet = Pet(name="Mochi", species="dog", age=3)
    task = FeedingTask(
        task_id="t-add-1",
        title="Dinner feeding",
        duration_minutes=15,
        base_priority=4,
        food_type="dry food",
        amount_grams=220,
        scheduled_time="19:00",
    )

    # 2. Act & Assert
    assert len(pet.tasks) == 0, "Pet task collection should initialize empty."

    pet.add_task(task)

    assert len(pet.tasks) == 1, "Adding a task must increment the pet's task count by exactly 1."
    assert pet.tasks[0].task_id == "t-add-1", "The stored task must match the appended instance."


def test_task_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Task(task_id="t1", title="Generic", duration_minutes=10, base_priority=3)


def test_medication_task_uses_custom_urgency_logic():
    task = MedicationTask(
        task_id="med-1",
        title="Medicine",
        duration_minutes=10,
        base_priority=5,
        dosage="1 tablet",
        dosage_window="morning",
    )

    assert task.calculate_urgency() > 0


def test_task_can_store_a_scheduled_time():
    task = FeedingTask(
        task_id="feed-1",
        title="Dinner",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="19:00",
    )

    assert task.scheduled_time == "19:00"


def test_scheduler_selects_tasks_that_fit_budget():
    owner = Owner(name="Jordan", daily_time_budget_minutes=30)
    pet = Pet(name="Mochi", species="dog", age=3)

    short_task = MedicationTask(
        task_id="med-1",
        title="Medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 pill",
        dosage_window="morning",
    )
    long_task = FeedingTask(
        task_id="feed-1",
        title="Dinner",
        duration_minutes=25,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
    )

    plan = SchedulerEngine().generate_plan(owner, pet, [long_task, short_task])

    assert plan == [short_task]


def test_scheduler_uses_pet_health_context_for_urgency():
    owner = Owner(name="Jordan", daily_time_budget_minutes=30)
    pet = Pet(
        name="Mochi",
        species="dog",
        age=3,
        health_flags=["pain", "needs monitoring"],
    )

    medication_task = MedicationTask(
        task_id="med-2",
        title="Pain relief",
        duration_minutes=10,
        base_priority=1,
        dosage="1 tablet",
        dosage_window="evening",
    )
    feeding_task = FeedingTask(
        task_id="feed-2",
        title="Dinner",
        duration_minutes=10,
        base_priority=8,
        food_type="wet food",
        amount_grams=200,
    )

    plan = SchedulerEngine().generate_plan(owner, pet, [feeding_task, medication_task])

    assert plan[0] == medication_task


def test_owner_context_and_global_plan_use_all_registered_tasks():
    owner = Owner(name="Jordan", daily_time_budget_minutes=10)
    first_pet = Pet(name="Mochi", species="dog", age=3)
    second_pet = Pet(name="Luna", species="cat", age=2)

    medication_task = MedicationTask(
        task_id="med-3",
        title="Medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 pill",
        dosage_window="morning",
    )
    feeding_task = FeedingTask(
        task_id="feed-3",
        title="Dinner",
        duration_minutes=8,
        base_priority=4,
        food_type="wet food",
        amount_grams=200,
    )

    first_pet.add_task(medication_task)
    second_pet.add_task(feeding_task)
    owner.add_pet(first_pet)
    owner.add_pet(second_pet)

    contextual_tasks = owner.get_all_tasks_contextual()
    assert contextual_tasks == [
        ScheduleItem(first_pet, medication_task),
        ScheduleItem(second_pet, feeding_task),
    ]

    plan = SchedulerEngine().generate_global_plan(owner)
    assert plan == [ScheduleItem(first_pet, medication_task)]


def test_pet_species_and_task_frequency_are_normalized_to_enums():
    pet = Pet(name="Mochi", species="DOG", age=3)
    task = FeedingTask(
        task_id="feed-4",
        title="Breakfast",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        frequency="daily",
    )

    assert pet.species is PetSpecies.DOG
    assert task.frequency is TaskFrequency.DAILY


def test_scheduler_sorts_tasks_by_time_and_keeps_unscheduled_last():
    scheduler = SchedulerEngine()
    late_task = FeedingTask(
        task_id="feed-5",
        title="Late feed",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="12:00",
    )
    early_task = MedicationTask(
        task_id="med-4",
        title="Early medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="07:30",
    )
    unscheduled_task = FeedingTask(
        task_id="feed-6",
        title="Unscheduled",
        duration_minutes=10,
        base_priority=3,
        food_type="wet food",
        amount_grams=150,
    )

    ordered = scheduler.sort_tasks_by_time([late_task, unscheduled_task, early_task])

    assert ordered == [early_task, late_task, unscheduled_task]


def test_scheduler_prioritizes_high_priority_tasks_before_time_order():
    scheduler = SchedulerEngine()
    low_priority_task = FeedingTask(
        task_id="feed-18",
        title="Low priority feed",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="06:00",
        priority="low",
    )
    high_priority_task = MedicationTask(
        task_id="med-14",
        title="High priority medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="07:00",
        priority="high",
    )

    ordered = scheduler.sort_tasks_by_time([low_priority_task, high_priority_task])

    assert ordered == [high_priority_task, low_priority_task]
    assert high_priority_task.priority is TaskPriority.HIGH


def test_scheduler_sort_by_time_uses_a_lambda_key_for_hh_mm_strings():
    scheduler = SchedulerEngine()
    late_task = FeedingTask(
        task_id="feed-9",
        title="Late feed",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="12:00",
    )
    early_task = MedicationTask(
        task_id="med-7",
        title="Early medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="07:30",
    )

    ordered = scheduler.sort_by_time([late_task, early_task])

    assert ordered == [early_task, late_task]


def test_scheduler_finds_next_available_slot_between_scheduled_tasks():
    scheduler = SchedulerEngine()
    first_task = MedicationTask(
        task_id="med-12",
        title="Morning medicine",
        duration_minutes=30,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="08:00",
    )
    second_task = FeedingTask(
        task_id="feed-17",
        title="Breakfast feeding",
        duration_minutes=20,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="09:00",
    )

    next_slot = scheduler.find_next_available_slot([first_task, second_task], duration_minutes=15)

    assert next_slot == time(8, 30)


def test_scheduler_filters_tasks_by_completion_status_and_pet_name():
    scheduler = SchedulerEngine()
    completed_task = FeedingTask(
        task_id="feed-10",
        title="Completed feed",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="09:00",
    )
    completed_task.mark_complete()
    pending_task = MedicationTask(
        task_id="med-8",
        title="Pending medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="10:00",
    )
    pending_task.pet_name = "Mochi"
    completed_task.pet_name = "Mochi"

    filtered = scheduler.filter_tasks(
        [completed_task, pending_task],
        completed=False,
        pet_name="Mochi",
    )

    assert filtered == [pending_task]


def test_llm_schedule_payload_is_parsed_into_typed_pydantic_response():
    raw_payload = (
        '{"plan": [{"task_id": "med-9", "title": "Evening medicine", '
        '"duration_minutes": 10, "base_priority": 9, "priority": "HIGH", '
        '"scheduled_time": "19:00", "frequency": "daily", '
        '"pet_name": "Mochi", "is_completed": false}]}'
    )

    parsed = parse_ai_schedule_response(raw_payload)

    assert isinstance(parsed, ScheduleAgentResponse)
    assert parsed.plan[0].priority is TaskPriority.HIGH
    assert parsed.plan[0].frequency is TaskFrequency.DAILY
    assert parsed.plan[0].base_priority == 9


def test_multimodal_agent_plan_from_image_uses_the_same_schema_bridge():
    agent = WolfieCareAgent()
    response = agent.plan_from_image(b"fake-jpeg-bytes", "Wolfie needs Otomax ear drops daily at 08:00.")

    task_schema = response["task_schema"]
    domain_task = response["domain_task"]

    assert task_schema.priority is TaskPriority.HIGH
    assert domain_task.priority is TaskPriority.HIGH
    assert domain_task.scheduled_time == "08:00"
    assert task_schema.to_domain_task().priority is TaskPriority.HIGH


def test_owner_from_dict_can_hydrate_seed_demo_payload():
    seed_payload = {
        "name": "Jordan",
        "daily_time_budget_minutes": 90,
        "pets": [
            {
                "name": "Wolfie",
                "species": "dog",
                "age": 4,
                "health_flags": ["pain"],
                "tasks": [
                    {
                        "task_id": "seed-med-1",
                        "title": "Gabapentin",
                        "duration_minutes": 10,
                        "base_priority": 8,
                        "pet_name": "Wolfie",
                        "is_completed": False,
                        "priority": "HIGH",
                        "scheduled_time": "08:00",
                        "due_date": None,
                        "frequency": "daily",
                        "is_recurring": True,
                        "recurring_occurrences": 2,
                        "type": "MedicationTask",
                        "dosage": "1 tablet",
                        "dosage_window": "morning",
                    }
                ],
            }
        ],
    }

    owner = Owner.from_dict(seed_payload)

    assert owner.name == "Jordan"
    assert len(owner.pets) == 1
    assert owner.pets[0].tasks[0].task_id == "seed-med-1"
    assert owner.pets[0].tasks[0].priority is TaskPriority.HIGH


def test_scheduler_filters_schedule_items_by_pet_and_completion_status():
    scheduler = SchedulerEngine()
    owner = Owner(name="Jordan", daily_time_budget_minutes=30)
    first_pet = Pet(name="Mochi", species="dog", age=3)
    second_pet = Pet(name="Luna", species="cat", age=2)

    first_task = FeedingTask(
        task_id="feed-7",
        title="Dinner",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
    )
    second_task = MedicationTask(
        task_id="med-5",
        title="Medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 pill",
        dosage_window="morning",
    )
    second_task.mark_complete()

    first_pet.add_task(first_task)
    second_pet.add_task(second_task)
    owner.add_pet(first_pet)
    owner.add_pet(second_pet)

    filtered = scheduler.filter_schedule_items(
        owner.get_all_tasks_contextual(),
        pet=first_pet,
        include_completed=False,
    )

    assert filtered == [ScheduleItem(first_pet, first_task)]


def test_owner_can_persist_state_to_json_and_restore(tmp_path):
    owner = Owner(name="Jordan", daily_time_budget_minutes=45)
    pet = Pet(name="Mochi", species="dog", age=3)
    task = MedicationTask(
        task_id="med-13",
        title="Morning medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="07:30",
    )
    pet.add_task(task)
    owner.add_pet(pet)

    filepath = tmp_path / "data.json"
    owner.save_to_json(str(filepath))
    restored_owner = Owner.load_from_json(str(filepath))

    assert restored_owner.name == owner.name
    assert restored_owner.daily_time_budget_minutes == owner.daily_time_budget_minutes
    assert len(restored_owner.pets) == 1

    restored_pet = restored_owner.pets[0]
    assert restored_pet.name == pet.name
    assert restored_pet.species is PetSpecies.DOG
    assert len(restored_pet.tasks) == 1

    restored_task = restored_pet.tasks[0]
    assert isinstance(restored_task, MedicationTask)
    assert restored_task.title == task.title
    assert restored_task.dosage == task.dosage
    assert restored_task.scheduled_time == task.scheduled_time


def test_scheduler_expands_recurring_tasks_and_detects_conflicts():
    scheduler = SchedulerEngine()
    pet = Pet(name="Mochi", species="dog", age=3)
    recurring_task = FeedingTask(
        task_id="feed-8",
        title="Breakfast",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="08:00",
        is_recurring=True,
        recurring_occurrences=2,
    )
    conflicting_task = MedicationTask(
        task_id="med-6",
        title="Medicine",
        duration_minutes=15,
        base_priority=8,
        dosage="1 pill",
        dosage_window="morning",
        scheduled_time="08:05",
    )

    expanded = scheduler.expand_recurring_tasks([recurring_task], max_occurrences=2)
    conflicts = scheduler.detect_conflicts([
        ScheduleItem(pet, recurring_task),
        ScheduleItem(pet, conflicting_task),
    ])

    assert len(expanded) == 2
    assert conflicts


def test_scheduler_detects_same_time_conflicts_for_different_pets():
    scheduler = Scheduler()
    first_pet = Pet(name="Mochi", species="dog", age=3)
    second_pet = Pet(name="Luna", species="cat", age=2)
    first_task = MedicationTask(
        task_id="med-9",
        title="Morning medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="08:00",
    )
    second_task = FeedingTask(
        task_id="feed-12",
        title="Breakfast feeding",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="08:00",
    )

    conflicts = scheduler.detect_conflicts([
        ScheduleItem(first_pet, first_task),
        ScheduleItem(second_pet, second_task),
    ])

    assert len(conflicts) == 1
    assert conflicts[0]["first"].task.task_id == "med-9"
    assert conflicts[0]["second"].task.task_id == "feed-12"


def test_sort_tasks_by_time_returns_chronological_order():
    scheduler = SchedulerEngine()
    morning_task = MedicationTask(
        task_id="med-10",
        title="Morning medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="07:30",
    )
    evening_task = FeedingTask(
        task_id="feed-13",
        title="Evening feeding",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="19:00",
    )
    unscheduled_task = FeedingTask(
        task_id="feed-14",
        title="Unscheduled feeding",
        duration_minutes=10,
        base_priority=3,
        food_type="wet food",
        amount_grams=150,
    )

    ordered = scheduler.sort_tasks_by_time([evening_task, unscheduled_task, morning_task])

    assert ordered == [morning_task, evening_task, unscheduled_task]


def test_marking_daily_task_complete_creates_next_day_occurrence():
    task = FeedingTask(
        task_id="feed-15",
        title="Daily breakfast",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="08:00",
        is_recurring=True,
        frequency="daily",
    )

    next_task = task.mark_complete()

    assert task.is_completed is True
    assert next_task is not None
    assert next_task.task_id == "feed-15-next"
    assert next_task.is_completed is False
    assert next_task.due_date == date.today() + timedelta(days=1)


def test_scheduler_flags_duplicate_scheduled_times_as_conflicts():
    scheduler = Scheduler()
    first_pet = Pet(name="Mochi", species="dog", age=3)
    second_pet = Pet(name="Luna", species="cat", age=2)
    first_task = MedicationTask(
        task_id="med-11",
        title="Morning medicine",
        duration_minutes=10,
        base_priority=8,
        dosage="1 tablet",
        dosage_window="morning",
        scheduled_time="08:00",
    )
    second_task = FeedingTask(
        task_id="feed-16",
        title="Breakfast feeding",
        duration_minutes=10,
        base_priority=4,
        food_type="dry food",
        amount_grams=200,
        scheduled_time="08:00",
    )

    conflicts = scheduler.detect_conflicts([
        ScheduleItem(first_pet, first_task),
        ScheduleItem(second_pet, second_task),
    ])

    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == "same scheduled time"
