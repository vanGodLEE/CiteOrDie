"""\

目标：解决 end_title 经常找不到 / 误匹配目录页 / 只比前缀导致 miss 的问题。

核心改动（3 件套）：
1) find_title_in_content_list 增加 start_from（从 start_idx+1 开始找 end_title，避免匹配到目录/页眉同名）
2) end_title 搜索页范围加 buffer（page_range 上界 +2 页）
3) is_title_contained 用滑动窗口最大相似度（不再只比 content 的前缀）

你可以把下面整个文件替换掉你当前的 TitleMatcher 文件，或按 diff 合并。
"""

import re
from typing import Optional, List, Tuple, Dict, Any
from difflib import SequenceMatcher
from html.parser import HTMLParser


class TitleMatcher:
    """标题模糊匹配器"""

    # -------------------------
    # 归一化与相似度
    # -------------------------
    @staticmethod
    def normalize_title(title: str) -> str:
        """标题归一化：小写、去空白、只保留中英文数字和§（白名单法更稳）。"""
        if not title:
            return ""
        s = title.lower()
        s = re.sub(r"\s+", "", s)
        # 只保留：数字/英文/中文/§
        s = re.sub(r"[^0-9a-z\u4e00-\u9fff§]+", "", s)
        # 可选：去掉常见编号前缀（比如 3.2 / 一、 / （一） 等）
        s = re.sub(r"^(第?[0-9一二三四五六七八九十]+[章节条款\.]*)", "", s)
        s = re.sub(r"^[（(]?[一二三四五六七八九十0-9]+[）)]?", "", s)
        s = re.sub(r"^[0-9]+[\.、]", "", s)
        return s

    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """SequenceMatcher 相似度（0-1）。"""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1, str2).ratio()

    @staticmethod
    def max_window_similarity(target: str, content: str, window_extra: int = 10) -> float:
        """滑动窗口最大相似度：解决标题不在 content 前缀时 miss 的问题。"""
        if not target or not content:
            return 0.0
        tlen = len(target)
        # 窗口长度 = 标题长度 + 少量冗余
        w = min(len(content), tlen + window_extra)
        best = 0.0
        step = 1 if w < 80 else 2  # 内容长一点时加快扫描

        # 遍历每个窗口
        for i in range(0, max(1, len(content) - w + 1), step):
            seg = content[i : i + w]
            s = TitleMatcher.calculate_similarity(target, seg)
            if s > best:
                best = s
                if best >= 0.99:
                    break
        return best

    @staticmethod
    def is_title_contained(target_title: str, content_text: str, similarity_threshold: float = 0.85) -> bool:
        """判断 target_title 是否匹配 content_text（包含 + 滑窗相似度）。"""
        norm_target = TitleMatcher.normalize_title(target_title)
        norm_content = TitleMatcher.normalize_title(content_text)

        if not norm_target or not norm_content:
            return False

        # 1) 精确包含
        if norm_target in norm_content:
            return True

        # 2) 滑窗最大相似度（不再只比前缀）
        best = TitleMatcher.max_window_similarity(norm_target, norm_content, window_extra=10)
        return best >= similarity_threshold

    # -------------------------
    # 在 content_list 里找标题
    # -------------------------
    @staticmethod
    def find_title_in_content_list(
        target_title: str,
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None,
        similarity_threshold: float = 0.85,
        start_from: int = 0,  # ✅ 新增：从哪个 index 开始扫描
    ) -> Optional[int]:
        """在 content_list 中查找目标标题索引。

        关键增强：
        - start_from：找 end_title 时从 start_idx+1 开始，避免匹配到目录/页眉同名
        - page_range：可限制页范围；若用于 end_title 建议上界加 buffer
        """
        # 预先归一化（可用于快速剪枝；这里暂时不做复杂剪枝）
        _ = TitleMatcher.normalize_title(target_title)

        # ✅ 注意：从 start_from 开始
        for i in range(max(0, start_from), len(content_list)):
            content = content_list[i]

            # 1) 页范围过滤
            if page_range:
                page_idx = content.get("page_idx", -1)
                if not (page_range[0] <= page_idx <= page_range[1]):
                    continue

            # 2) 提取文本
            content_text = TitleMatcher._extract_content_text(content)
            if not content_text:
                continue

            # 3) 匹配
            if TitleMatcher.is_title_contained(target_title, content_text, similarity_threshold):
                return i

        return None

    @staticmethod
    def _extract_content_text(content: Dict[str, Any]) -> str:
        """从 content 项中提取用于匹配的文本。"""
        content_type = content.get("type", "")

        if content_type == "text":
            return content.get("text", "")

        if content_type == "header":
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

        return ""

    # -------------------------
    # 由标题确定内容区间
    # -------------------------
    @staticmethod
    def find_content_range_by_titles(
        start_title: str,
        end_title: Optional[str],
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None,
        similarity_threshold: float = 0.85,
    ) -> List[Dict[str, Any]]:
        """根据起始/结束标题在 content_list 中切内容区间。

        关键增强：
        - start_title 用 page_range 限定即可（你说 start 一般能找到）
        - end_title：
          * 搜索页范围加 buffer：end_page + 2
          * 从 start_idx+1 开始找：避免目录页/页眉同名
        """
        # 1) start
        start_idx = TitleMatcher.find_title_in_content_list(
            start_title,
            content_list,
            page_range=page_range,
            similarity_threshold=similarity_threshold,
            start_from=0,
        )
        if start_idx is None:
            return []

        # 2) end
        if end_title:
            # ✅ end_title 搜索范围放宽：上界 +2 页
            end_search_range = None
            if page_range:
                end_search_range = (page_range[0], page_range[1] + 2)

            end_idx = TitleMatcher.find_title_in_content_list(
                end_title,
                content_list,
                page_range=end_search_range,
                similarity_threshold=similarity_threshold,
                start_from=start_idx + 1,  # ✅ 关键：从 start 后面开始找 end
            )

            if end_idx is None:
                # 找不到 end_title：退化到 page_range 末尾 或全文末尾
                if page_range:
                    for i in range(len(content_list) - 1, -1, -1):
                        p = content_list[i].get("page_idx", -1)
                        if page_range[0] <= p <= page_range[1]:
                            end_idx = i + 1
                            break
                    else:
                        end_idx = len(content_list)
                else:
                    end_idx = len(content_list)
        else:
            # 没有 end_title：取 page_range 末尾 或全文末尾
            if page_range:
                for i in range(len(content_list) - 1, -1, -1):
                    p = content_list[i].get("page_idx", -1)
                    if page_range[0] <= p <= page_range[1]:
                        end_idx = i + 1
                        break
                else:
                    end_idx = len(content_list)
            else:
                end_idx = len(content_list)

        # 3) slice（不包含 start/end 标题本身）
        result: List[Dict[str, Any]] = []
        for i in range(start_idx + 1, min(end_idx, len(content_list))):
            c = content_list[i]
            if page_range:
                p = c.get("page_idx", -1)
                if not (page_range[0] <= p <= page_range[1]):
                    continue
            result.append(c)

        return result

    # -------------------------
    # 生成原文（可选，保持你原来的实现）
    # -------------------------
    @staticmethod
    def extract_text_from_contents(contents: List[Dict[str, Any]]) -> str:
        text_parts = []
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
                parts = []
                if caption:
                    cap_text = " ".join(caption)
                    if img_path:
                        parts.append(f"【表格：{img_path}】{cap_text}")
                    else:
                        parts.append(f"【表格】{cap_text}")
                else:
                    parts.append(f"【表格：{img_path}】" if img_path else "【表格】")

                if table_body:
                    table_text = _convert_html_table_to_text(table_body)
                    if table_text:
                        parts.append(table_text)

                if len(parts) > 1:
                    text_parts.append("\n".join(parts))

        return "\n\n".join(text_parts)


# -------------------------
# bbox 提取（保持你原来的实现）
# -------------------------

def extract_bbox_positions(contents: List[Dict[str, Any]]) -> List[List[int]]:
    positions = []
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
    """bbox 版本也同样修 end_title：buffer + start_from=start_idx+1"""

    start_idx = TitleMatcher.find_title_in_content_list(
        start_title,
        content_list,
        page_range=page_range,
        similarity_threshold=similarity_threshold,
        start_from=0,
    )

    if start_idx is None:
        # fallback：整个页范围
        if page_range is None:
            return []
        positions = []
        for c in content_list:
            p = c.get("page_idx", -1)
            if page_range[0] <= p <= page_range[1]:
                bbox = c.get("bbox")
                if bbox and len(bbox) == 4 and c.get("page_idx") is not None:
                    positions.append([c.get("page_idx")] + bbox)
        return positions

    # end
    if end_title:
        end_search_range = None
        if page_range:
            end_search_range = (page_range[0], page_range[1] + 2)

        end_idx = TitleMatcher.find_title_in_content_list(
            end_title,
            content_list,
            page_range=end_search_range,
            similarity_threshold=similarity_threshold,
            start_from=start_idx + 1,
        )

        if end_idx is None:
            end_idx = len(content_list)
    else:
        end_idx = len(content_list)

    # bbox slice：包含 start 标题 bbox，不包含 end 标题 bbox
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


# -------------------------
# 便捷函数（保持你原来的接口）
# -------------------------

def find_title_match(title: str, content_list: List[Dict[str, Any]], page_range: Optional[Tuple[int, int]] = None) -> Optional[int]:
    return TitleMatcher.find_title_in_content_list(title, content_list, page_range)


def extract_content_by_title_range(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None,
) -> str:
    contents = TitleMatcher.find_content_range_by_titles(start_title, end_title, content_list, page_range)
    return TitleMatcher.extract_text_from_contents(contents)


def _convert_html_table_to_text(html_table: str) -> str:
    if not html_table:
        return ""
    try:
        parser = HTMLTableParser()
        parser.feed(html_table)
        if not parser.rows:
            return ""
        lines = []
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


class HTMLTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.current_cell = []
        self.in_table = False
        self.in_row = False
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag):
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

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)
