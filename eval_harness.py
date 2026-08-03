"""
Wolfie OS - Evaluation & Reliability Harness

Executes structured evaluation vectors against the agentic RAG layer AND the
deterministic core. Every vector asserts a real, observable outcome (not merely
"did it run"), then logs reasoning traces to ai_interactions.md.

Vector A - Prompt-to-priority extraction grounded in retrieved RAG context.
Vector B - Real interval collision: overlapping tasks are detected and the slot
           finder reroutes to a genuinely non-overlapping window.
Vector C - Real guardrail intercept: malformed output raises a Pydantic
           ValidationError and never reaches the scheduler.
"""

from datetime import time

from pydantic import ValidationError

from agent import WolfieCareAgent
from pawpal_system import (
    FeedingTask,
    Pet,
    ScheduleItem,
    SchedulerEngine,
    TaskPriority,
)
from schemas import ExtractedTaskSchema


def run_evaluation_suite() -> int:
    print("=" * 60)
    print("🐾 WOLFIE OS — APPLIED AI EVALUATION SUITE")
    print("=" * 60)

    agent = WolfieCareAgent()
    engine = SchedulerEngine()
    passed = 0
    total = 3
    trace_logs = []

    # ---- Vector A: High-priority RAG medication extraction ---------------------
    prompt_a = "Wolfie needs Otomax ear drops daily at 08:00."
    try:
        res_a = agent.plan_care_task(prompt_a)
        task_a = res_a["task_schema"]
        domain_a = task_a.to_domain_task()
        if task_a.priority is TaskPriority.HIGH and domain_a.scheduled_time_value == time(8, 0):
            print("\nVector A: PASS | Otomax extracted -> HIGH priority, 08:00, "
                  "bridged to a native domain task")
            passed += 1
        else:
            print(f"\nVector A: FAIL | priority={task_a.priority.value}, "
                  f"time={domain_a.scheduled_time_label}")
        trace_logs.append(res_a["reasoning_trace"])
    except Exception as e:
        print(f"\nVector A: FAIL with exception: {e}")

    # ---- Vector B: Real interval collision + rerouting -------------------------
    prompt_b = "Cleo the cat needs feeding at 17:30 daily."
    try:
        res_b = agent.plan_care_task(prompt_b)
        pet = Pet(name="Cleo", species="cat", age=2)
        first = res_b["task_schema"].to_domain_task(task_id="b-existing")
        # A second task deliberately overlaps the first's window.
        clash = FeedingTask(
            task_id="b-clash", title="Overlapping meal",
            duration_minutes=30, base_priority=5,
            scheduled_time=first.scheduled_time,
        )
        items = [ScheduleItem(pet=pet, task=first), ScheduleItem(pet=pet, task=clash)]
        conflicts = engine.detect_conflicts(items)
        reroute = engine.find_next_available_slot([first, clash], duration_minutes=30)
        first_end_minutes = (first.scheduled_time_value.hour * 60
                             + first.scheduled_time_value.minute + first.duration_minutes)
        reroute_minutes = reroute.hour * 60 + reroute.minute if reroute else -1
        if conflicts and reroute is not None and reroute_minutes >= first_end_minutes:
            print(f"Vector B: PASS | collision detected, rerouted to "
                  f"{reroute.strftime('%H:%M')} (clear of {first.scheduled_time_label})")
            passed += 1
        else:
            print(f"Vector B: FAIL | conflicts={len(conflicts)}, reroute={reroute}")
        trace_logs.append(res_b["reasoning_trace"])
    except Exception as e:
        print(f"Vector B: FAIL with exception: {e}")

    # ---- Vector C: Real guardrail interception ---------------------------------
    # A malformed 24-hour time must be rejected by the Pydantic guardrail before it
    # can mutate any schedule state.
    try:
        ExtractedTaskSchema(
            pet_name="Wolfie", title="Invalid dose", species="dog",
            priority="high", frequency="daily", start_time_str="25:99",
        )
        print("Vector C: FAIL | guardrail admitted an invalid 25:99 time")
    except ValidationError:
        print("Vector C: PASS | invalid time '25:99' rejected by Pydantic guardrail "
              "(no state mutation)")
        passed += 1
    except Exception as e:
        print(f"Vector C: FAIL with unexpected exception: {e}")

    pass_rate = (passed / total) * 100

    print("\n" + "=" * 60)
    print(f"EVALUATION SUMMARY: {passed}/{total} Passed ({pass_rate:.1f}%)")
    print("=" * 60)

    _export_traces(trace_logs, passed, total, pass_rate)
    print("📄 Traces successfully exported to ai_interactions.md\n")
    return passed


def _export_traces(trace_logs, passed, total, pass_rate) -> None:
    with open("ai_interactions.md", "w", encoding="utf-8") as f:
        f.write("# Wolfie OS — Agent Reasoning & Interaction Traces\n\n")
        f.write(f"**Evaluation Pass Rate:** {passed}/{total} ({pass_rate:.1f}%)\n\n")
        f.write("## Intermediate Reasoning Logs\n\n")
        for i, trace in enumerate(trace_logs, 1):
            f.write(f"### Vector Test Case {i}\n")
            f.write(f"- **Input:** `{trace['input_prompt']}`\n")
            f.write(f"- **Retrieved RAG Context:** `{trace['retrieved_rag_context']}`\n")
            f.write(f"- **RAG Rules Applied:** `{trace['rag_applied']}`\n")
            f.write(f"- **Pydantic Model Payload:** ```json\n{trace['extracted_pydantic']}\n```\n\n")


if __name__ == "__main__":
    run_evaluation_suite()
