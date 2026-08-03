# Model Card & Responsible AI Reflection — Wolfie OS

## 1. System Overview & Model Architecture
- **System Name:** Wolfie OS (v1.0.0 Applied AI System)
- **Base Architecture:** Hybrid Agentic-Deterministic Engine (Local RAG + Pydantic Schema Guardrails + Python $O(N^2)$ Conflict Engine).
- **Primary LLM Integration:** Unstructured-to-Structured translation engine with local vector retrieval over `docs/vet_guidelines.md`.

## 2. AI Collaboration & Development Reflection
### How AI Was Used During Development
AI tools (Claude Code CLI, GitHub Copilot, Gemini) were paired with during system design to:
1. Formalize Pydantic data validation schemas (`schemas.py`) ensuring strict 1:1 Enum mapping.
2. Draft and refine continuous interval overlap algorithms ($O(N^2)$ pairwise checking).
3. Build the automated evaluation suite (`eval_harness.py`) to benchmark system reliability.

### Helpful vs. Flawed AI Suggestions
- **Helpful AI Suggestion:** Decoupling schedule math from LLM inference entirely. Using Pydantic validators to coerce raw model outputs directly into native Python `datetime.time` objects and typed Enums (`SpeciesEnum`, `TaskPriorityEnum`, `TaskFrequencyEnum`) eliminated non-deterministic time math errors.
- **Flawed AI Suggestion:** An early AI prompt draft suggested letting the LLM calculate the `next_available_slot` directly via natural language. During testing, the model hallucinated overlapping 15-minute windows and miscalculated 24-hour time boundaries (e.g., treating `09:30` as after `10:00`). This suggestion was rejected in favor of a deterministic $O(N \log N)$ window-slicing solver in `pawpal_system.py`.

## 3. System Limitations & Failure Modes
1. **Unseen Pet Species:** The domain core strictly enforces `SpeciesEnum` (`dog`, `cat`, `bird`, `reptile`). Inputting exotic species will trigger a validation error unless explicitly added to the Enum contract.
2. **Ambiguous Time Prompts:** Unstructured prompts lacking explicit times (e.g., "give medication later today") fall back to default window slots (`08:00` or `10:00`) rather than querying the user for clarification.
3. **Complex Multi-Drug Interactions:** While RAG retrieves guidelines from `docs/vet_guidelines.md`, the system is not a licensed clinical diagnostic tool and requires human owner verification for prescription changes.

## 4. Guardrails & Safety Mechanisms
- **Input Validation:** Pydantic validators reject malformed time strings before state updates.
- **Output Guardrails:** Single-field priority mapping ensures priority is represented purely as an Enum (`HIGH`, `MEDIUM`, `LOW`), preventing dual-input ambiguity or inconsistent urgency weights.
- **Deterministic Override:** All scheduled tasks must pass through `detect_conflicts()` in `pawpal_system.py`. If a collision is detected, the AI recommendation is overridden by the deterministic slot finder.