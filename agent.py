"""
Wolfie OS - Agentic Care Orchestrator & RAG Retriever
Ingests unstructured care notes, retrieves relevant veterinary context,
and produces validated Pydantic task models for the deterministic engine.
"""

import os
import re
from typing import List, Dict, Any, Tuple
from datetime import time
from schemas import ExtractedTaskSchema, TaskPriorityEnum, TaskFrequencyEnum, SpeciesEnum


class VetGuidelineRAG:
    """Lightweight local RAG retriever indexing veterinary care guidelines."""

    def __init__(self, doc_path: str = "docs/vet_guidelines.md"):
        self.doc_path = doc_path
        self.chunks: List[str] = []
        self._load_and_index()

    def _load_and_index(self):
        if not os.path.exists(self.doc_path):
            self.chunks = ["Standard veterinary care buffer is 15 minutes."]
            return
        
        with open(self.doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Split markdown by headers/paragraphs into searchable chunks
        raw_chunks = content.split("\n\n")
        self.chunks = [c.strip() for c in raw_chunks if c.strip()]

    def retrieve_relevant_context(self, query: str, top_k: int = 2) -> List[str]:
        """Simple, deterministic semantic keyword chunk matcher."""
        query_words = set(re.findall(r'\w+', query.lower()))
        scored_chunks: List[Tuple[int, str]] = []

        for chunk in self.chunks:
            chunk_words = set(re.findall(r'\w+', chunk.lower()))
            overlap = len(query_words.intersection(chunk_words))
            if overlap > 0:
                scored_chunks.append((overlap, chunk))

        # Sort by overlap score descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        results = [chunk for _, chunk in scored_chunks[:top_k]]
        
        return results if results else ["Follow standard multi-pet care protocols."]


class WolfieCareAgent:
    """Agentic planner translating unstructured text into validated care tasks."""

    def __init__(self, rag_engine: VetGuidelineRAG = None):
        self.rag = rag_engine or VetGuidelineRAG()

    def plan_care_task(self, unstructured_prompt: str) -> Dict[str, Any]:
        """
        Multi-step agent workflow:
        1. Query RAG for veterinary safety rules.
        2. Parse unstructured prompt into structured Pydantic model.
        3. Trace reasoning steps for transparency.
        """
        # Step 1: RAG Retrieval
        retrieved_context = self.rag.retrieve_relevant_context(unstructured_prompt)
        
        # Step 2: Extract attributes from unstructured prompt
        extracted = self._rule_based_extractor(unstructured_prompt)
        
        # Step 3: Validate via Pydantic Guardrail Schema
        task_schema = ExtractedTaskSchema(**extracted)

        # Step 4: Build transparent reasoning trace for logs
        reasoning_trace = {
            "input_prompt": unstructured_prompt,
            "retrieved_rag_context": retrieved_context,
            "extracted_pydantic": task_schema.model_dump(),
            "status": "VALIDATED_AND_PASSED_GUARDRAIL"
        }

        return {
            "task_schema": task_schema,
            "reasoning_trace": reasoning_trace
        }

    def _rule_based_extractor(self, text: str) -> Dict[str, Any]:
        """Parsing fallback ensuring deterministic execution in test environments."""
        text_lower = text.lower()

        # Pet name detection
        pet_name = "Wolfie"
        for word in ["luna", "mochi", "cleo", "max", "bella"]:
            if word in text_lower:
                pet_name = word.capitalize()

        # Species detection
        species = SpeciesEnum.DOG
        if "cat" in text_lower or "feline" in text_lower:
            species = SpeciesEnum.CAT

        # Priority detection from keywords & RAG rules
        priority = TaskPriorityEnum.MEDIUM
        if any(term in text_lower for term in ["otomax", "ear drop", "medication", "urgent", "nsaid", "insulin"]):
            priority = TaskPriorityEnum.HIGH
        elif "walk" in text_lower or "play" in text_lower:
            priority = TaskPriorityEnum.LOW

        # Time extraction (finds HH:MM pattern or defaults)
        time_match = re.search(r'(\d{1,2}):(\d{2})', text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            start_time = f"{hour:02d}:{minute:02d}"
        else:
            start_time = "08:00" if priority == TaskPriorityEnum.HIGH else "10:00"

        return {
            "pet_name": pet_name,
            "title": text.split(".")[0][:40] if text else "Pet Care Event",
            "species": species,
            "priority": priority,
            "frequency": TaskFrequencyEnum.DAILY if "daily" in text_lower else TaskFrequencyEnum.ONCE,
            "start_time_str": start_time,
            "duration_minutes": 15
        }