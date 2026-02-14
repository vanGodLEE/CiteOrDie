"""
Section slicer – locate title boundaries in a MinerU content list and
extract the content / bounding-box positions between them.

Main capabilities:
* Fuzzy title matching via ``TitleMatcher`` (normalization + sliding-window
  similarity with ``SequenceMatcher``).
* **Robust** multi-strategy title matching with cascading fallback.
* Slicing a ``content_list`` by start/end title into a content range or a
  list of bbox positions.
* Page-range-based fallback text extraction.
* Converting HTML ``<table>`` fragments to plain text for downstream use.
"""

import re
from typing import Optional, List, Tuple, Dict, Any
from difflib import SequenceMatcher
from html.parser import HTMLParser
from loguru import logger


# ===========================================================================
# TitleMatcher – fuzzy title lookup in content lists
# ===========================================================================

class TitleMatcher:
    """Fuzzy title matcher for MinerU content-list items."""

    # -----------------------------------------------------------------------
    # Normalization & similarity
    # -----------------------------------------------------------------------

    @staticmethod
    def normalize_title(title: str) -> str:
        """
        Normalize a title for comparison.

        Steps: lowercase → collapse whitespace → keep only alphanumeric /
        CJK / ``§`` → strip common CJK numbering prefixes.
        """
        if not title:
            return ""
        s = title.lower()
        s = re.sub(r"\s+", "", s)
        # Keep: digits, ASCII letters, CJK ideographs, §
        s = re.sub(r"[^0-9a-z\u4e00-\u9fff§]+", "", s)
        # Strip common CJK / numeric section prefixes
        s = re.sub(r"^(第?[0-9一二三四五六七八九十]+[章节条款\.]*)", "", s)
        s = re.sub(r"^[（(]?[一二三四五六七八九十0-9]+[）)]?", "", s)
        s = re.sub(r"^[0-9]+[\.、]", "", s)
        return s

    @staticmethod
    def normalize_title_light(title: str) -> str:
        """
        Light normalization – lowercase and collapse whitespace only.

        Unlike :meth:`normalize_title`, this preserves punctuation and
        numbering prefixes (e.g. ``"3.1.2"``, ``"第三章"``), providing
        more precise disambiguation for titled sections.
        """
        if not title:
            return ""
        s = title.lower()
        s = re.sub(r"\s+", "", s)
        return s

    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """Return the ``SequenceMatcher`` ratio (0.0 – 1.0)."""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1, str2).ratio()

    @staticmethod
    def max_window_similarity(
        target: str,
        content: str,
        window_extra: int = 10,
    ) -> float:
        """
        Sliding-window maximum similarity.

        Scans *content* with a window slightly wider than *target* and
        returns the highest similarity score found.  This avoids misses
        when the title does not appear at the start of *content*.
        """
        if not target or not content:
            return 0.0
        tlen = len(target)
        w = min(len(content), tlen + window_extra)
        best = 0.0
        step = 1 if w < 80 else 2  # speed up for long content

        for i in range(0, max(1, len(content) - w + 1), step):
            seg = content[i: i + w]
            s = TitleMatcher.calculate_similarity(target, seg)
            if s > best:
                best = s
                if best >= 0.99:
                    break
        return best

    @staticmethod
    def is_title_contained(
        target_title: str,
        content_text: str,
        similarity_threshold: float = 0.85,
    ) -> bool:
        """
        Check whether *target_title* matches *content_text*.

        Returns ``True`` on exact containment **or** when the sliding-window
        similarity meets *similarity_threshold*.
        """
        norm_target = TitleMatcher.normalize_title(target_title)
        norm_content = TitleMatcher.normalize_title(content_text)

        if not norm_target or not norm_content:
            return False

        # 1) Exact containment
        if norm_target in norm_content:
            return True

        # 2) Sliding-window similarity
        best = TitleMatcher.max_window_similarity(
            norm_target, norm_content, window_extra=10,
        )
        return best >= similarity_threshold

    # -----------------------------------------------------------------------
    # Title lookup in content_list
    # -----------------------------------------------------------------------

    @staticmethod
    def find_title_in_content_list(
        target_title: str,
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None,
        similarity_threshold: float = 0.85,
        start_from: int = 0,
    ) -> Optional[int]:
        """
        Find the index of *target_title* inside *content_list*.

        Args:
            target_title: Title string to search for.
            content_list: MinerU content items.
            page_range: Optional ``(start_page, end_page)`` filter (0-based).
            similarity_threshold: Minimum similarity for a match.
            start_from: Index to begin scanning from (useful when searching
                for an end-title after the start-title has been found).

        Returns:
            Index into *content_list*, or ``None`` if not found.
        """
        for i in range(max(0, start_from), len(content_list)):
            content = content_list[i]

            # Page-range filter
            if page_range:
                page_idx = content.get("page_idx", -1)
                if not (page_range[0] <= page_idx <= page_range[1]):
                    continue

            # Extract comparable text
            content_text = TitleMatcher._extract_content_text(content)
            if not content_text:
                continue

            # Match
            if TitleMatcher.is_title_contained(
                target_title, content_text, similarity_threshold,
            ):
                return i

        return None

    @staticmethod
    def find_title_in_content_list_robust(
        target_title: str,
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None,
        similarity_threshold: float = 0.85,
        start_from: int = 0,
    ) -> Optional[int]:
        """
        Robust multi-strategy title finding with cascading fallback.

        Unlike :meth:`find_title_in_content_list`, this method tries
        several progressively relaxed strategies before giving up:

        1. Standard match within page range (existing behavior).
        2. Header-type items only with light normalization within page range
           (catches formatting differences, prefers actual headings).
        3. Standard match with expanded page range (±2 pages – handles
           PageIndex / MinerU page misalignment).
        4. Lower similarity threshold (0.70) with expanded page range
           (handles significant text differences).
        5. Standard match with wide page range (±5 pages – last resort
           title search before giving up).

        Returns:
            Index into *content_list*, or ``None`` if all strategies fail.
        """
        # Strategy 1: standard match (original behavior)
        result = TitleMatcher.find_title_in_content_list(
            target_title, content_list, page_range,
            similarity_threshold, start_from,
        )
        if result is not None:
            return result

        # Strategy 2: header-type preference with light normalization
        light_target = TitleMatcher.normalize_title_light(target_title)
        if light_target and page_range:
            for i in range(max(0, start_from), len(content_list)):
                content = content_list[i]
                page_idx = content.get("page_idx", -1)
                if not (page_range[0] <= page_idx <= page_range[1]):
                    continue
                if content.get("type") != "header":
                    continue
                content_text = TitleMatcher._extract_content_text(content)
                if not content_text:
                    continue
                light_content = TitleMatcher.normalize_title_light(content_text)
                if (light_target in light_content) or (light_content in light_target):
                    logger.debug(
                        f"[Robust S2] header+light match: '{target_title}' "
                        f"-> index {i}, page {page_idx}"
                    )
                    return i

        # Strategy 3: expanded page range (±2 pages)
        if page_range:
            expanded = (max(0, page_range[0] - 2), page_range[1] + 2)
            result = TitleMatcher.find_title_in_content_list(
                target_title, content_list, expanded,
                similarity_threshold, start_from,
            )
            if result is not None:
                logger.debug(
                    f"[Robust S3] expanded range: '{target_title}' "
                    f"-> index {result}, range {expanded}"
                )
                return result

        # Strategy 4: lower threshold (0.70) with expanded range
        if page_range:
            expanded = (max(0, page_range[0] - 2), page_range[1] + 2)
            result = TitleMatcher.find_title_in_content_list(
                target_title, content_list, expanded,
                0.70, start_from,
            )
            if result is not None:
                logger.debug(
                    f"[Robust S4] low threshold: '{target_title}' "
                    f"-> index {result}, threshold=0.70"
                )
                return result

        # Strategy 5: wide page range (±5 pages)
        if page_range:
            wide = (max(0, page_range[0] - 5), page_range[1] + 5)
            result = TitleMatcher.find_title_in_content_list(
                target_title, content_list, wide,
                similarity_threshold, start_from,
            )
            if result is not None:
                logger.debug(
                    f"[Robust S5] wide range: '{target_title}' "
                    f"-> index {result}, range {wide}"
                )
                return result

        logger.warning(
            f"[Robust] all 5 strategies failed for: '{target_title}'"
        )
        return None

    @staticmethod
    def _extract_content_text(content: Dict[str, Any]) -> str:
        """
        Extract the matchable text from a single content item.

        Handles ``text``, ``header``, ``list``, ``image`` (caption),
        ``table`` (caption), and unknown types (fallback to ``"text"`` key).
        """
        content_type = content.get("type", "")

        if content_type in ("text", "header"):
            return content.get("text", "")

        if content_type == "list":
            items = content.get("list_items", [])
            return " ".join(items) if items else ""

        if content_type == "image":
            caption = content.get("image_caption", [])
            return " ".join(caption) if caption else ""

        if content_type == "table":
            caption = content.get("table_caption", [])
            return " ".join(caption) if caption else ""

        # Fallback for unknown content types: try the "text" key
        return content.get("text", "")

    # -----------------------------------------------------------------------
    # Content-range slicing by title boundaries
    # -----------------------------------------------------------------------

    @staticmethod
    def find_content_range_by_titles(
        start_title: str,
        end_title: Optional[str],
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None,
        similarity_threshold: float = 0.85,
    ) -> List[Dict[str, Any]]:
        """
        Slice *content_list* between *start_title* and *end_title*.

        When searching for *end_title*, two heuristics are applied:
        1. The page upper bound is extended by 2 pages (buffer).
        2. Scanning starts after the start-title index to avoid
           false matches in the table-of-contents / running headers.

        Returns:
            Content items **between** (exclusive) the two title
            boundaries.  An empty list if *start_title* is not found.
        """
        # --- Locate start title ---
        start_idx = TitleMatcher.find_title_in_content_list(
            start_title,
            content_list,
            page_range=page_range,
            similarity_threshold=similarity_threshold,
            start_from=0,
        )
        if start_idx is None:
            return []

        # --- Locate end title ---
        end_idx = _resolve_end_index(
            end_title,
            content_list,
            page_range,
            similarity_threshold,
            start_idx,
        )

        # --- Slice (excluding both title items) ---
        result: List[Dict[str, Any]] = []
        for i in range(start_idx + 1, min(end_idx, len(content_list))):
            c = content_list[i]
            if page_range:
                p = c.get("page_idx", -1)
                if not (page_range[0] <= p <= page_range[1]):
                    continue
            result.append(c)

        return result

    # -----------------------------------------------------------------------
    # Text assembly
    # -----------------------------------------------------------------------

    @staticmethod
    def extract_text_from_contents(contents: List[Dict[str, Any]]) -> str:
        """
        Concatenate matchable text from a list of content items.

        Handles text, headers, lists, images, and tables (including
        HTML table body conversion).
        """
        text_parts: List[str] = []
        for content in contents:
            t = content.get("type", "")

            if t == "text":
                s = content.get("text", "")
                if s:
                    text_parts.append(s)

            elif t == "header":
                s = content.get("text", "")
                if s:
                    text_parts.append(f"# {s}")

            elif t == "list":
                items = content.get("list_items", [])
                if items:
                    text_parts.append("\n".join(items))

            elif t == "image":
                img_path = content.get("img_path", "")
                cap = content.get("image_caption", [])
                if img_path:
                    cap_text = " ".join(cap) if cap else img_path.split("/")[-1]
                    text_parts.append(f"![{cap_text}]({img_path})")

            elif t == "table":
                caption = content.get("table_caption", [])
                table_body = content.get("table_body", "")
                img_path = content.get("img_path", "")
                parts: List[str] = []

                if caption:
                    cap_text = " ".join(caption)
                    if img_path:
                        parts.append(f"[Table: {img_path}] {cap_text}")
                    else:
                        parts.append(f"[Table] {cap_text}")
                else:
                    parts.append(f"[Table: {img_path}]" if img_path else "[Table]")

                if table_body:
                    table_text = _convert_html_table_to_text(table_body)
                    if table_text:
                        parts.append(table_text)

                if len(parts) > 1:
                    text_parts.append("\n".join(parts))

        return "\n\n".join(text_parts)


# ===========================================================================
# Content extraction by known start index (avoids redundant title search)
# ===========================================================================

def extract_content_between(
    start_idx: int,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None,
    similarity_threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    """
    Extract content items between a **known** *start_idx* and an *end_title*.

    Unlike :meth:`TitleMatcher.find_content_range_by_titles`, this function
    skips the start-title lookup entirely (the caller already resolved it via
    :meth:`TitleMatcher.find_title_in_content_list_robust`).  This avoids the
    common failure mode where a robust match cannot be reproduced by a second
    standard-method call.

    Args:
        start_idx: Already-resolved index of the start-title item.
        end_title: Title that marks the end boundary (exclusive), or ``None``.
        content_list: Full MinerU content list.
        page_range: Optional page filter (0-based).  When ``None`` the content
            is not filtered by page.
        similarity_threshold: Passed to :func:`_resolve_end_index` for the
            end-title search.

    Returns:
        Content items **between** (exclusive of) the start-title and the
        resolved end boundary.
    """
    end_idx = _resolve_end_index(
        end_title, content_list, page_range,
        similarity_threshold, start_idx,
    )

    result: List[Dict[str, Any]] = []
    for i in range(start_idx + 1, min(end_idx, len(content_list))):
        c = content_list[i]
        if page_range:
            p = c.get("page_idx", -1)
            if not (page_range[0] <= p <= page_range[1]):
                continue
        result.append(c)

    return result


# ===========================================================================
# Page-range fallback text extraction
# ===========================================================================

def extract_text_by_page_range(
    content_list: List[Dict[str, Any]],
    start_page: int,
    end_page: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Fallback extraction: collect **all** content items within a page range
    and assemble their text.

    This is the last-resort mechanism used when title matching completely
    fails.  It provides text for clause extraction (better than nothing)
    and bbox positions for evidence highlighting.

    Args:
        content_list: Full MinerU content list.
        start_page: Start page (0-based inclusive).
        end_page: End page (0-based inclusive).

    Returns:
        ``(assembled_text, matching_content_items)``
    """
    matching = [
        c for c in content_list
        if start_page <= c.get("page_idx", -1) <= end_page
    ]
    text = TitleMatcher.extract_text_from_contents(matching)
    return text, matching


# ===========================================================================
# Bbox extraction helpers
# ===========================================================================

def extract_bbox_positions(contents: List[Dict[str, Any]]) -> List[List[int]]:
    """
    Collect ``[page_idx, x0, y0, x1, y1]`` from every content item that
    carries a valid 4-element bbox.
    """
    positions: List[List[int]] = []
    for content in contents:
        bbox = content.get("bbox")
        page_idx = content.get("page_idx")
        if bbox and page_idx is not None and len(bbox) == 4:
            positions.append([page_idx] + bbox)
    return positions


def extract_bbox_positions_with_titles(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None,
    similarity_threshold: float = 0.85,
) -> List[List[int]]:
    """
    Like :func:`extract_bbox_positions`, but first narrows the content
    range using *start_title* / *end_title* boundaries.

    Falls back to the full *page_range* when *start_title* is not found.
    """
    start_idx = TitleMatcher.find_title_in_content_list(
        start_title,
        content_list,
        page_range=page_range,
        similarity_threshold=similarity_threshold,
        start_from=0,
    )

    if start_idx is None:
        # Fallback: collect all bboxes inside page_range
        if page_range is None:
            return []
        positions: List[List[int]] = []
        for c in content_list:
            p = c.get("page_idx", -1)
            if page_range[0] <= p <= page_range[1]:
                bbox = c.get("bbox")
                if bbox and len(bbox) == 4 and c.get("page_idx") is not None:
                    positions.append([c["page_idx"]] + bbox)
        return positions

    # Locate end boundary
    end_idx = _resolve_end_index(
        end_title,
        content_list,
        page_range,
        similarity_threshold,
        start_idx,
    )

    # Collect bboxes (includes start-title item, excludes end-title item)
    positions = []
    actual_end_idx = max(end_idx, start_idx + 1)
    for i in range(start_idx, min(actual_end_idx, len(content_list))):
        c = content_list[i]
        if page_range:
            p = c.get("page_idx", -1)
            if not (page_range[0] <= p <= page_range[1]):
                continue
        bbox = c.get("bbox")
        page_idx = c.get("page_idx")
        if bbox and page_idx is not None and len(bbox) == 4:
            positions.append([page_idx] + bbox)

    return positions


# ===========================================================================
# Convenience wrappers (preserve backward-compatible call signatures)
# ===========================================================================

def find_title_match(
    title: str,
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None,
) -> Optional[int]:
    """Shorthand for :meth:`TitleMatcher.find_title_in_content_list`."""
    return TitleMatcher.find_title_in_content_list(title, content_list, page_range)


def extract_content_by_title_range(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None,
) -> str:
    """Find content between two titles and return assembled text."""
    contents = TitleMatcher.find_content_range_by_titles(
        start_title, end_title, content_list, page_range,
    )
    return TitleMatcher.extract_text_from_contents(contents)


# ===========================================================================
# Internal helpers
# ===========================================================================

_END_TITLE_PAGE_BUFFER: int = 2  # extra pages when searching for end title


def _resolve_end_index(
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]],
    similarity_threshold: float,
    start_idx: int,
) -> int:
    """
    Determine the end-boundary index for a content-range slice.

    If *end_title* is given, search with a +2-page buffer starting after
    *start_idx*.  Otherwise (or on miss) fall back to the last item
    within *page_range*, or the end of *content_list*.
    """
    if end_title:
        end_search_range = None
        if page_range:
            end_search_range = (page_range[0], page_range[1] + _END_TITLE_PAGE_BUFFER)

        end_idx = TitleMatcher.find_title_in_content_list(
            end_title,
            content_list,
            page_range=end_search_range,
            similarity_threshold=similarity_threshold,
            start_from=start_idx + 1,
        )

        if end_idx is not None:
            return end_idx

    # Fallback: last item inside page_range, or end of list
    return _last_index_in_page_range(content_list, page_range)


def _last_index_in_page_range(
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]],
) -> int:
    """Return one-past-the-last index within *page_range*."""
    if page_range:
        for i in range(len(content_list) - 1, -1, -1):
            p = content_list[i].get("page_idx", -1)
            if page_range[0] <= p <= page_range[1]:
                return i + 1
    return len(content_list)


def _convert_html_table_to_text(html_table: str) -> str:
    """Best-effort conversion of an HTML ``<table>`` to pipe-delimited text."""
    if not html_table:
        return ""
    try:
        parser = _HTMLTableParser()
        parser.feed(html_table)
        if not parser.rows:
            return ""
        lines: List[str] = []
        for row in parser.rows:
            if row:
                line = " | ".join(cell.strip() for cell in row if cell.strip())
                if line:
                    lines.append(line)
        return "\n".join(lines)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html_table)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class _HTMLTableParser(HTMLParser):
    """Minimal HTML table parser that collects rows of cell text."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self.current_row: List[str] = []
        self.current_cell: List[str] = []
        self.in_table = False
        self.in_row = False
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag = tag.lower()
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            cell_text = "".join(self.current_cell).strip()
            self.current_row.append(cell_text)
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)
