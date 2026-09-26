from typing import Any

from pydantic import BaseModel, Field


class EvidenceOut(BaseModel):
    edge_id: int
    type: str
    extractor: str = Field(description="manifest | import | docker | compose | language | git | …")
    evidence: str | None
    confidence: float
    document_id: int | None
    path: str | None
    source_name: str | None
    line: int | None
    chunk_ids: list[int]
    meta: dict[str, Any]


class RelatedOut(BaseModel):
    node_id: int
    kind: str
    name: str
    meta: dict[str, Any]
    confidence: float
    evidence: list[EvidenceOut]


class StackTech(BaseModel):
    name: str
    category: str | None
    via: list[str] = Field(description="How it was detected: manifest, import, language, …")


class ProjectSummary(BaseModel):
    id: int
    name: str
    source_id: int | None
    source_name: str
    root: str
    manifests: list[str]
    technologies: list[StackTech]
    package_count: int


class NodeOut(BaseModel):
    id: int
    kind: str
    name: str
    source_id: int | None
    meta: dict[str, Any]


class NodeDetail(NodeOut):
    """Everything one hop away, grouped by relation. `outgoing` and `incoming` are keyed by
    edge type (uses, depends_on, authored, mentions, links_to, tagged)."""

    outgoing: dict[str, list[RelatedOut]] = Field(default_factory=dict)
    incoming: dict[str, list[RelatedOut]] = Field(default_factory=dict)


class GraphNode(BaseModel):
    id: int
    kind: str
    name: str
    depth: int
    meta: dict[str, Any]


class GraphEdge(BaseModel):
    src: int
    dst: int
    type: str
    evidence: int = Field(description="Pieces of evidence behind this relation")
    confidence: float


class Neighbourhood(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
