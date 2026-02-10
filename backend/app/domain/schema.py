"""
Core data models and LangGraph state definitions.

This module contains:
* **ClauseItem** – structured clause extracted from a document.
* **PageIndexNode / PageIndexDocument** – recursive document-tree model.
* **DocumentAnalysisState** – global LangGraph workflow state.
* **SectionState** – per-section worker state.
* **create_matrix_id** – clause ID generator.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator


# ===========================================================================
# State reducers
# ===========================================================================

def _merge_errors(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    """Reducer for ``error_message``: concatenate when both parallel nodes fail."""
    if not existing:
        return new
    if not new:
        return existing
    return f"{existing}; {new}"


# ===========================================================================
# ClauseItem – structured clause
# ===========================================================================

class ClauseItem(BaseModel):
    """
    Structured clause extracted from a document.

    Core fields: type, actor, action, object, condition, deadline, metric.
    Identity / location fields: matrix_id, original_text, section_id,
    section_title, page_number, positions.
    Visual fields: image_caption, table_caption, img_path.
    """

    # Structured fields
    type: str = Field(
        ...,
        description="Clause type: obligation | requirement | prohibition | deliverable | deadline | penalty | definition",
    )
    actor: Optional[str] = Field(
        None,
        description="Responsible party: supplier | buyer | provider | client | system | organization | role",
    )
    action: Optional[str] = Field(
        None,
        description="Action verb: submit | provide | ensure | record | comply | …",
    )
    object: Optional[str] = Field(
        None,
        description="Target object: document | feature | KPI | material | …",
    )
    condition: Optional[str] = Field(
        None,
        description="Trigger condition (if / when / unless …)",
    )
    deadline: Optional[str] = Field(
        None,
        description="Time constraint: specific date, relative period, or recurrence",
    )
    metric: Optional[str] = Field(
        None,
        description="Quantitative metric: value, range, or comparison (>=, <=, …)",
    )

    # Identity / location
    matrix_id: str = Field(..., description="Unique clause ID, e.g. '{section_id}-CLS-001'")
    original_text: str = Field(..., description="Verbatim clause text")
    section_id: str = Field(..., description="Parent section identifier")
    section_title: str = Field(..., description="Parent section title")
    page_number: int = Field(..., description="Page number (1-based)")

    # Visual content
    image_caption: Optional[str] = Field(
        None,
        description="Image description (vision-model output, if clause originates from an image)",
    )
    table_caption: Optional[str] = Field(
        None,
        description="Table description (structured data, if clause originates from a table)",
    )
    img_path: Optional[str] = Field(
        None,
        description="Relative path to image/table asset (e.g. 'images/xxx.jpg')",
    )

    # Positional data
    positions: List[List[int]] = Field(
        default_factory=list,
        description="Bbox list: [[page_idx, x1, y1, x2, y2], …] (MinerU 0-based page index)",
    )


# ===========================================================================
# PageIndexNode / PageIndexDocument – document tree
# ===========================================================================

class PageIndexNode(BaseModel):
    """
    Recursive document-tree node produced by PageIndex.

    Each node may carry extracted clauses and precise original-text
    content with bounding-box positions.
    """

    # PageIndex fields
    node_id: Optional[str] = Field(None, description="Node ID assigned by PageIndex (e.g. '0001')")
    structure: Optional[str] = Field(None, description="Section number (e.g. '2.1', '2.1.1')")
    title: str = Field(..., description="Section title (without numbering)")
    start_index: int = Field(..., description="Start page (1-based)")
    end_index: int = Field(..., description="End page (1-based)")
    summary: Optional[str] = Field(None, description="PageIndex-generated summary (page-level)")
    text: Optional[str] = Field(None, description="PageIndex-generated full text (optional)")

    # Tree structure
    nodes: List[PageIndexNode] = Field(default_factory=list, description="Child nodes")

    # Precise original text (filled by text-filler node)
    original_text: Optional[str] = Field(None, description="Extracted original text (line-level)")

    # Bbox positions (filled by text-filler node)
    positions: List[List[int]] = Field(
        default_factory=list,
        description="Bbox list: [[page_idx, x1, y1, x2, y2], …]",
    )

    # Clauses extracted for this node
    clauses: List[ClauseItem] = Field(default_factory=list, description="Clauses belonging to this node")

    # Auxiliary
    path: Optional[str] = Field(None, description="Human-readable node path")

    # ------------------------------------------------------------------
    # Tree traversal helpers
    # ------------------------------------------------------------------

    def is_leaf(self) -> bool:
        """Return ``True`` if this node has no children."""
        return len(self.nodes) == 0

    def get_all_clauses_recursive(self) -> List[ClauseItem]:
        """Collect clauses from this node and all descendants."""
        all_clauses = list(self.clauses)
        for child in self.nodes:
            all_clauses.extend(child.get_all_clauses_recursive())
        return all_clauses

    def get_leaf_nodes(self) -> List[PageIndexNode]:
        """Return all leaf nodes in the subtree."""
        if self.is_leaf():
            return [self]
        leaves: List[PageIndexNode] = []
        for child in self.nodes:
            leaves.extend(child.get_leaf_nodes())
        return leaves

    def get_all_nodes(self) -> List[PageIndexNode]:
        """Return this node plus all descendants (pre-order)."""
        all_nodes: List[PageIndexNode] = [self]
        for child in self.nodes:
            all_nodes.extend(child.get_all_nodes())
        return all_nodes

    def find_next_sibling(self, siblings: List[PageIndexNode]) -> Optional[PageIndexNode]:
        """Find the next sibling in *siblings* (or ``None``)."""
        try:
            idx = siblings.index(self)
            if idx < len(siblings) - 1:
                return siblings[idx + 1]
        except ValueError:
            pass
        return None

    def count_total_clauses(self) -> int:
        """Count clauses in the entire subtree."""
        return len(self.get_all_clauses_recursive())


class PageIndexDocument(BaseModel):
    """Complete document structure produced by PageIndex."""

    doc_name: str = Field(..., description="Document file name")
    doc_description: Optional[str] = Field(None, description="Document-level description (PageIndex)")
    structure: List[PageIndexNode] = Field(..., description="Root nodes of the document tree")

    def get_all_leaf_nodes(self) -> List[PageIndexNode]:
        """Return every leaf node across all root nodes."""
        leaves: List[PageIndexNode] = []
        for root in self.structure:
            leaves.extend(root.get_leaf_nodes())
        return leaves

    def count_total_clauses(self) -> int:
        """Count clauses across the entire document."""
        return sum(root.count_total_clauses() for root in self.structure)


# ===========================================================================
# LangGraph state definitions
# ===========================================================================

class DocumentAnalysisState(TypedDict):
    """
    Global LangGraph workflow state.

    Data flow:
    1. Input: ``pdf_path``
    2. PageIndex parser → ``pageindex_document`` (document tree)
    3. MinerU parser → ``mineru_content_list`` (blocks + images + tables)
    4. Text fillers (parallel) → fill ``original_text`` on each node
    5. Enrichers (parallel) → extract clauses per leaf node
    6. Auditor → aggregate into ``final_matrix``
    7. Evidence locator → assign ``positions`` to each clause
    """

    # Input
    pdf_path: str
    use_mock: bool                          # use mock data (dev only)
    task_id: Optional[str]                  # for progress reporting

    # PageIndex output
    pageindex_document: Optional[PageIndexDocument]

    # MinerU output
    mineru_result: Optional[Dict[str, Any]]
    mineru_content_list: List[Dict[str, Any]]
    mineru_output_dir: Optional[str]

    # DEPRECATED – compatibility fields (kept to avoid breaking existing code)
    content_list: List[Dict[str, Any]]
    markdown: str
    toc: List
    toc_tree: Optional[Any]
    target_sections: List

    # Extractor output (operator.add enables parallel append)
    clauses: Annotated[List[ClauseItem], operator.add]

    # Auditor output
    final_matrix: List[ClauseItem]

    # Metadata
    processing_start_time: Optional[float]
    processing_end_time: Optional[float]
    error_message: Annotated[Optional[str], _merge_errors]


# Backward-compatible alias
TenderAnalysisState = DocumentAnalysisState


class SectionState(TypedDict):
    """
    Per-section worker state passed to enricher nodes.

    Each enricher receives one leaf ``pageindex_node`` together with
    the ``task_id`` and ``mineru_output_dir`` for progress reporting
    and vision-model access.
    """

    pageindex_node: Optional[PageIndexNode]
    task_id: Optional[str]
    mineru_output_dir: Optional[str]

    # DEPRECATED – compatibility fields
    section_node: Optional[Any]
    content_blocks: Optional[List]
    section_id: Optional[str]
    section_title: Optional[str]
    section_plan: Optional[Any]

    # Worker output
    clauses: List[ClauseItem]


# ===========================================================================
# Helpers
# ===========================================================================

def create_matrix_id(section_id: str, sequence: int) -> str:
    """
    Generate a clause matrix ID.

    Args:
        section_id: Section identifier (e.g. ``"3.1.2"``).
        sequence: 1-based sequence number.

    Returns:
        Formatted ID such as ``"3.1.2-CLS-001"``.
    """
    return f"{section_id}-CLS-{sequence:03d}"
