import json
from pathlib import Path

from agent import WolfieCareAgent, VetGuidelineRAG
from pawpal_system import MedicationTask, TaskPriority
from schemas import ExtractedTaskSchema


def test_image_extraction_valid_schema():
    agent = WolfieCareAgent()
    result = agent.plan_care_task_from_image(
        b"fake-image-bytes",
        user_notes="Wolfie needs Otomax ear drops daily at 08:00.",
    )

    task_schema = result["task_schema"]
    assert isinstance(task_schema, ExtractedTaskSchema)
    assert task_schema.pet_name == "Wolfie"
    assert task_schema.title == "Wolfie needs Otomax ear drops daily at 08:00."
    assert task_schema.start_time_str == "08:00"


def test_image_extraction_bridges_to_domain_task():
    agent = WolfieCareAgent()
    result = agent.plan_care_task_from_image(
        b"fake-image-bytes",
        user_notes="Cleo needs Gabapentin with food at 20:00.",
    )

    task_schema = result["task_schema"]
    domain_task = task_schema.to_domain_task()
    assert isinstance(domain_task, MedicationTask)
    assert domain_task.priority is TaskPriority.HIGH
    assert domain_task.scheduled_time == "20:00"


def test_seed_demo_data_creation():
    from scripts.seed_demo_data import main

    main()
    data_path = Path("data/data.json")

    assert data_path.exists(), "The demo seed export should create data/data.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    assert payload["name"] == "Jordan"
    assert len(payload["pets"]) == 2
    assert any(pet["name"] == "Wolfie" for pet in payload["pets"])
    assert any(pet["name"] == "Cleo" for pet in payload["pets"])


def test_emergency_triage_rag_indexing():
    rag = VetGuidelineRAG(doc_path="docs/vet_guidelines.md", emergency_doc_path="docs/emergency_triage.md")
    indexed = rag.emergency_chunks
    assert indexed, "Emergency triage rules should be indexed into the local retrieval corpus"
    assert any("GDV" in chunk or "bloat" in chunk.lower() for chunk in indexed)
    assert any("urinary obstruction" in chunk.lower() or "urinary blockage" in chunk.lower() for chunk in indexed)
