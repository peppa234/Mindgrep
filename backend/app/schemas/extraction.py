"""Schemas the extraction model must fill. The same Pydantic class is the JSON schema sent to
the provider (structured output) and the validator for what comes back."""

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedConcept(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    kind: Literal["technology", "concept"]
    evidence: str = Field(max_length=300, description="A short quote copied from the text")


class ConceptExtraction(BaseModel):
    concepts: list[ExtractedConcept] = Field(default_factory=list, max_length=15)
