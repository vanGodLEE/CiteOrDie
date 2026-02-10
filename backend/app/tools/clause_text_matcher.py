"""
Clause-text matcher – multi-strategy text matching for evidence location.

Given a clause's ``original_text`` (which may be paraphrased by the LLM),
this module locates the corresponding bounding-box positions inside a
node's ``content_list`` using a four-level fallback strategy:

1. **Exact** – normalized text equality.
2. **Similarity** – ``SequenceMatcher`` ratio >= threshold.
3. **Substring** – clause text found as a substring of concatenated content.
4. **Keyword** – keyword overlap ratio >= threshold (uses *jieba* when
   available, plain regex split otherwise).
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from loguru import logger
from difflib import SequenceMatcher
import re


class RequirementTextMatcher:
    """
    Multi-strategy matcher that maps a clause's original text to
    content-list positions.

    Class-level thresholds can be adjusted per deployment if needed.
    """

    SIMILARITY_THRESHOLD: float = 0.85  # strategy-2 similarity floor
    KEYWORD_THRESHOLD: float = 0.70     # strategy-4 keyword-overlap floor

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @staticmethod
    def find_requirement_positions(
        requirement_text: str,
        node_content_list: List[Dict[str, Any]],
        node_positions: List[List[int]],
    ) -> List[List[int]]:
        """
        Locate *requirement_text* in *node_content_list* and return positions.

        Tries four strategies in order (exact → similarity → substring →
        keyword) and returns the result of the first one that succeeds.

        Args:
            requirement_text: The clause's ``original_text``.
            node_content_list: Content items scoped to the node.
            node_positions: The node's position list (for validation).

        Returns:
            ``[[page_idx, x1, y1, x2, y2], ...]`` or empty list.
        """
        if not requirement_text or not node_content_list:
            return []

        logger.debug(f"Matching clause text: {requirement_text[:50]}...")
        logger.debug(f"Search scope: {len(node_content_list)} content items")

        # Strategy 1 – exact (normalized equality)
        positions = RequirementTextMatcher._exact_match(
            requirement_text, node_content_list,
        )
        if positions:
            logger.debug(f"Strategy 1 hit (exact): {len(positions)} position(s)")
            return positions

        # Strategy 2 – similarity (>= 85 %)
        positions = RequirementTextMatcher._similarity_match(
            requirement_text, node_content_list,
        )
        if positions:
            logger.debug(f"Strategy 2 hit (similarity): {len(positions)} position(s)")
            return positions

        # Strategy 3 – substring
        positions = RequirementTextMatcher._substring_match(
            requirement_text, node_content_list,
        )
        if positions:
            logger.debug(f"Strategy 3 hit (substring): {len(positions)} position(s)")
            return positions

        # Strategy 4 – keyword overlap (>= 70 %)
        positions = RequirementTextMatcher._keyword_match(
            requirement_text, node_content_list,
        )
        if positions:
            logger.debug(f"Strategy 4 hit (keyword): {len(positions)} position(s)")
            return positions

        logger.warning(f"All matching strategies failed: {requirement_text[:50]}...")
        return []

    # ------------------------------------------------------------------
    # Strategy 1 – exact match (after normalization)
    # ------------------------------------------------------------------

    @staticmethod
    def _exact_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]],
    ) -> List[List[int]]:
        """
        Normalized exact match.

        Supports ``type="text"`` (compare text field) and ``type="list"``
        (compare each list item).
        """
        normalized_req = _normalize_text(requirement_text)

        for content in content_list:
            content_type = content.get("type")

            if content_type == "text":
                content_text = content.get("text", "")
                if normalized_req == _normalize_text(content_text):
                    logger.debug(f"Exact match on text: '{content_text[:30]}...'")
                    return [_build_position(content)]

            elif content_type == "list":
                for item in content.get("list_items", []):
                    if normalized_req == _normalize_text(item):
                        logger.debug(f"Exact match on list item: '{item[:30]}...'")
                        return [_build_position(content)]

        return []

    # ------------------------------------------------------------------
    # Strategy 2 – similarity match
    # ------------------------------------------------------------------

    @staticmethod
    def _similarity_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]],
    ) -> List[List[int]]:
        """Best-similarity match among text-type content items."""
        normalized_req = _normalize_text(requirement_text)
        threshold = RequirementTextMatcher.SIMILARITY_THRESHOLD

        best_match: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for content in content_list:
            if content.get("type") != "text":
                continue

            content_text = content.get("text", "")
            score = SequenceMatcher(
                None, normalized_req, _normalize_text(content_text),
            ).ratio()

            if score > best_score:
                best_score = score
                best_match = content

        if best_score >= threshold and best_match is not None:
            logger.debug(
                f"Similarity match: score={best_score:.2f}, "
                f"text='{best_match.get('text', '')[:30]}...'"
            )
            return [_build_position(best_match)]

        return []

    # ------------------------------------------------------------------
    # Strategy 3 – substring match
    # ------------------------------------------------------------------

    @staticmethod
    def _substring_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]],
    ) -> List[List[int]]:
        """
        Find the clause text as a substring of concatenated content.

        Handles cases where the LLM quoted only a fragment of the
        original paragraph, or where the text spans multiple content items.
        """
        normalized_req = _normalize_text(requirement_text)

        # Build a flat text with an index mapping back to content items
        full_text = ""
        content_map: List[Tuple[int, int, Dict[str, Any]]] = []

        for content in content_list:
            content_type = content.get("type")

            if content_type == "text":
                text = _normalize_text(content.get("text", ""))
                start = len(full_text)
                full_text += text
                content_map.append((start, len(full_text), content))

            elif content_type == "list":
                combined = "".join(
                    _normalize_text(item) for item in content.get("list_items", [])
                )
                start = len(full_text)
                full_text += combined
                content_map.append((start, len(full_text), content))

        pos = full_text.find(normalized_req)
        if pos == -1:
            return []

        # Collect all content items that overlap with the match span
        req_end = pos + len(normalized_req)
        positions: List[List[int]] = []

        for start, end, content in content_map:
            if not (end <= pos or start >= req_end):
                positions.append(_build_position(content))

        if positions:
            logger.debug(
                f"Substring match: {len(positions)} content item(s), "
                f"span=[{pos}, {req_end}]"
            )

        return positions

    # ------------------------------------------------------------------
    # Strategy 4 – keyword overlap
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]],
    ) -> List[List[int]]:
        """
        Keyword-overlap match.

        Useful when the LLM paraphrased the original text or the clause
        is a summary rather than a verbatim quote.
        """
        req_keywords = _extract_keywords(requirement_text)
        if not req_keywords:
            return []

        threshold = RequirementTextMatcher.KEYWORD_THRESHOLD
        best_match: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for content in content_list:
            content_type = content.get("type")

            if content_type == "text":
                content_text = content.get("text", "")
            elif content_type == "list":
                content_text = "".join(content.get("list_items", []))
            else:
                continue

            content_keywords = _extract_keywords(content_text)
            matched = len(req_keywords & content_keywords)
            score = matched / len(req_keywords) if req_keywords else 0.0

            if score > best_score:
                best_score = score
                best_match = content

        if best_score >= threshold and best_match is not None:
            preview = best_match.get("text", "")[:30] or str(best_match.get("list_items", []))[:30]
            logger.debug(f"Keyword match: score={best_score:.2f}, text='{preview}...'")
            return [_build_position(best_match)]

        return []


# ===========================================================================
# Internal helpers
# ===========================================================================

def _normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    1. Strip leading numbering markers (e.g. ``(1)``, ``①``, ``a.``).
    2. Remove all whitespace.
    3. Remove all punctuation (keep letters, digits, CJK).
    4. Lowercase.
    """
    # Strip leading numbering patterns
    text = re.sub(
        r'^[\(（]\s*[0-9一二三四五六七八九十百千万零壹贰叁肆伍陆柒捌玖拾佰仟萬零]+\s*[\)）]',
        '', text,
    )
    text = re.sub(
        r'^[0-9一二三四五六七八九十百千万零壹贰叁肆伍陆柒捌玖拾佰仟萬零]+\s*[.、。）\)]',
        '', text,
    )
    text = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]', '', text)
    text = re.sub(r'^[a-zA-Z]\s*[\)）.]', '', text)

    text = re.sub(r'\s+', '', text)        # collapse whitespace
    text = re.sub(r'[^\w]', '', text)       # strip punctuation
    text = text.lower()
    return text


def _build_position(content: Dict[str, Any]) -> List[int]:
    """
    Build a ``[page_idx, x1, y1, x2, y2]`` from a content item.

    Returns ``[0, 0, 0, 0, 0]`` when the bbox is missing or malformed.
    """
    page_idx = content.get("page_idx", 0)
    bbox = content.get("bbox", [0, 0, 0, 0])

    if not isinstance(bbox, list) or len(bbox) != 4:
        logger.warning(f"Invalid bbox: {bbox}")
        bbox = [0, 0, 0, 0]

    return [page_idx] + bbox


def _extract_keywords(text: str) -> Set[str]:
    """
    Extract keywords from *text* (simple tokenisation + stop-word removal).

    Uses *jieba* for Chinese segmentation when available; falls back to a
    plain regex split otherwise.
    """
    try:
        import jieba

        words = jieba.cut(text)
        stopwords = {
            '的', '了', '是', '在', '和', '与', '等', '或', '及',
            '、', '，', '。', '：', '；', '？', '！', '\u201c', '\u201d',
            '需', '要', '应', '可', '能', '将', '为', '以', '从',
            '个', '项', '条', '款', '类', '种', '次', '中', '等等',
        }
        return {
            w.strip() for w in words
            if w.strip() and len(w.strip()) > 1 and w not in stopwords
        }

    except ImportError:
        logger.warning("jieba not installed, using simple tokenizer")
        words = re.findall(r'[\w]+', text)
        return {w for w in words if len(w) > 1}


# ===========================================================================
# Node content extraction by position
# ===========================================================================

def extract_node_content_list(
    node_positions: List[List[int]],
    full_content_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract content items from *full_content_list* that match *node_positions*.

    For each position ``[page_idx, x1, y1, x2, y2]``, the first content
    item on the same page with an approximately equal bbox is selected.

    Args:
        node_positions: ``[[page_idx, x1, y1, x2, y2], ...]``.
        full_content_list: The full MinerU content list.

    Returns:
        Matched content items (order follows *node_positions*).
    """
    if not node_positions:
        logger.warning("Empty node_positions, cannot extract content")
        return []

    node_contents: List[Dict[str, Any]] = []

    for pos in node_positions:
        if len(pos) < 5:
            logger.warning(f"Invalid position: {pos}")
            continue

        page_idx = pos[0]
        bbox = pos[1:5]

        for content in full_content_list:
            if content.get("page_idx") == page_idx:
                content_bbox = content.get("bbox")
                if content_bbox and len(content_bbox) == 4:
                    if _bbox_equal(content_bbox, bbox):
                        node_contents.append(content)
                        break

    logger.debug(
        f"Extracted {len(node_contents)} content item(s) "
        f"from {len(node_positions)} position(s)"
    )
    return node_contents


def _bbox_equal(
    bbox1: List[float],
    bbox2: List[int],
    tolerance: float = 0.1,
) -> bool:
    """Check whether two bboxes are equal within *tolerance*."""
    if len(bbox1) != 4 or len(bbox2) != 4:
        return False
    return all(abs(bbox1[i] - bbox2[i]) <= tolerance for i in range(4))
