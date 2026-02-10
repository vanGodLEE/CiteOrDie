"""
LangGraph node – clause aggregator.

Collects all clauses produced by parallel extractor workers, sorts
them by section, normalises whitespace, and writes ``final_matrix``.

No deduplication is performed: identical clause text from different
sections is intentionally preserved because the surrounding context
differs.
"""

from typing import List

from loguru import logger

from app.domain.schema import ClauseItem, DocumentAnalysisState


def clause_aggregator_node(state: DocumentAnalysisState) -> dict:
    """
    Aggregate, sort, and normalise all extracted clauses.

    Steps:
    1. Collect clauses from state (appended by parallel workers).
    2. Sort by ``section_id`` then ``matrix_id``.
    3. Strip leading/trailing whitespace.

    No deduplication – different sections may legitimately contain
    overlapping clause text.

    Returns:
        ``{"final_matrix": [ClauseItem, …]}``
    """
    logger.info("=" * 50)
    logger.info("Clause aggregator started")
    logger.info("=" * 50)

    task_id = state.get("task_id")
    if task_id:
        from app.services.task_tracker import TaskTracker
        TaskTracker.update_task(
            task_id, progress=85, message="Running quality checks and aggregation...",
        )

    clauses: List[ClauseItem] = state.get("clauses", [])

    if not clauses:
        logger.warning("No clauses to aggregate")
        return {"final_matrix": []}

    logger.info(f"Aggregating {len(clauses)} clause(s) (no dedup)")

    sorted_clauses = _sort_clauses(clauses)
    final_matrix = _normalize_clauses(sorted_clauses)

    logger.info(f"Aggregation complete: {len(final_matrix)} clause(s) in final matrix")
    _log_summary(final_matrix)

    return {"final_matrix": final_matrix}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sort_clauses(clauses: List[ClauseItem]) -> List[ClauseItem]:
    """Sort clauses by ``section_id`` then ``matrix_id``."""
    return sorted(clauses, key=lambda c: (c.section_id, c.matrix_id))


def _normalize_clauses(clauses: List[ClauseItem]) -> List[ClauseItem]:
    """Strip leading/trailing whitespace from text fields."""
    for c in clauses:
        c.original_text = c.original_text.strip()
        c.section_title = c.section_title.strip()
    return clauses


def _log_summary(clauses: List[ClauseItem]) -> None:
    """Log per-section clause counts."""
    section_counts: dict[str, int] = {}
    for c in clauses:
        key = f"{c.section_id} {c.section_title}"
        section_counts[key] = section_counts.get(key, 0) + 1

    logger.info("Clause summary:")
    logger.info(f"  Total: {len(clauses)} clause(s)")
    logger.info(f"  Sections: {len(section_counts)}")

    top = sorted(section_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    logger.info("  Top 5 sections by clause count:")
    for section, count in top:
        logger.info(f"    {section}: {count}")


# Backward-compatible alias
auditor_node = clause_aggregator_node
