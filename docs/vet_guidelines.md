# Wolfie OS — Veterinary Care & Administration Guidelines

## 1. Medication Administration Protocols
- **Otitis externa treatments (Otomax / Posatex):** Must be dosed twice daily, separated by at least 8 hours. A safe implementation requires the agent to anchor the next dose window to the previous dose and never schedule two applications closer than 8 hours apart.
- **Ear Drops (Otomax / Posatex):** Administer every 12 hours. Must be spaced at least 30 minutes away from oral feeding routines to avoid stress-induced head shaking during meals.
- **NSAIDs (Meloxicam / Carprofen):** Must ALWAYS be administered with or immediately after a full meal. Never on an empty stomach.
- **Gabapentin:** Must be given with food. Recommended spacing is 8 to 12 hours for chronic pain/anxiety management.

## 2. Dietary & Multi-Pet Feeding Protocols
- **Multi-Pet Feeding Separation:** Cats and dogs must have separated feeding windows (minimum 15-minute staggered start) to prevent food aggression and dietary cross-contamination.
- **Medication Window Buffer:** Always allow a 15-minute continuous window buffer for medical tasks to allow proper dosage verification.

## 3. High-Priority Care Alerts
- Any task involving **insulin, prescription heart medication, or anti-seizure protocols** defaults strictly to `TaskPriority.HIGH` and requires immediate conflict-checking against all other pet schedules.
- When a retrieval rule references a medication-specific temporal bound, the agent must inject that exact timing constraint into the prompt before selecting a task slot.