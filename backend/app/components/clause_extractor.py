"""
LangGraph node – clause extractor (text + vision).

Processes a single leaf :class:`PageIndexNode`, extracting actionable
clauses from its ``original_text`` via an LLM and, optionally, from
embedded images via a vision model.
"""

import json
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from app.services.task_tracker import TaskTracker
from app.domain.schema import ClauseItem, PageIndexNode, SectionState, create_matrix_id
from app.domain.settings import settings
from app.services.llm_client import get_llm_client
from app.tools.progress_helper import log_step


# =========================================================================
# Main node function
# =========================================================================

def clause_extractor_node(state: SectionState) -> Dict[str, Any]:
    """
    Extract clauses from a single document-tree node.

    Reads:
        ``state["pageindex_node"]``, ``state["task_id"]``,
        ``state["mineru_output_dir"]``

    Writes:
        ``state["clauses"]`` – list of :class:`ClauseItem` (appended to
        the global state via ``operator.add``).

    Workflow:
    1. Extract **text** clauses from ``original_text`` using the LLM.
    2. Detect image references in the Markdown content.
    3. If images exist, call the vision model for **visual** clauses.
    4. Merge, re-number, and return all clauses.
    """
    node: PageIndexNode | None = state.get("pageindex_node")
    task_id: str | None = state.get("task_id")
    mineru_output_dir: str | None = state.get("mineru_output_dir")

    if not node:
        logger.warning("No pageindex_node in state – skipping")
        return {"clauses": []}

    logger.info(
        f"Processing node: {node.title} (pages {node.start_index}-{node.end_index})"
    )

    if task_id:
        TaskTracker.log_progress(task_id, f"Extracting clauses: {node.title}", 50)

    try:
        content = _prepare_node_content(node)

        # ---- Step 1: text clauses ----
        text_clauses: List[ClauseItem] = []

        if content and content.strip():
            logger.info(
                f"Node '{node.title}' content length: {len(content)} chars – "
                "extracting text clauses"
            )
            log_step(task_id, f"Analysing section: {node.title} ({len(content)} chars)")

            llm = get_llm_client()
            log_step(task_id, "Calling LLM for structured clause extraction...")

            prompt = _build_extraction_prompt(node, content)

            class ClauseList(BaseModel):
                """Wrapper for LLM structured output."""
                items: List[ClauseItem] = Field(
                    default_factory=list, description="提取的条款列表",
                )

            # NOTE: The system message is in Chinese intentionally – it is
            # an LLM prompt and changing the language may affect quality.
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的文档分析专家，擅长从各类文档中提取结构化条款。",
                },
                {"role": "user", "content": prompt},
            ]

            result = llm.structured_completion(
                messages=messages,
                response_model=ClauseList,
                model=settings.extractor_llm_name,
                temperature=0.1,
            )

            text_clauses = result.items if result else []
            logger.info(f"Text clauses extracted: {len(text_clauses)}")
            log_step(task_id, f"Text clauses: {len(text_clauses)}")
        else:
            logger.info(f"Node '{node.title}' has no text content")

        # ---- Step 2: visual clauses (if images present) ----
        visual_clauses: List[ClauseItem] = []

        if mineru_output_dir and content:
            image_paths = _extract_image_paths_from_markdown(content, mineru_output_dir)

            if image_paths:
                logger.info(
                    f"Node '{node.title}' contains {len(image_paths)} image(s)"
                )
                log_step(
                    task_id,
                    f"Found {len(image_paths)} figure(s) – starting vision analysis",
                )

                llm = get_llm_client()
                visual_clauses = _extract_clauses_from_images(
                    image_paths=image_paths,
                    node=node,
                    llm_client=llm,
                    task_id=task_id,
                )
                logger.info(f"Visual clauses extracted: {len(visual_clauses)}")
                log_step(task_id, f"Visual clauses: {len(visual_clauses)}")

        # ---- Step 3: merge and re-number ----
        all_clauses = text_clauses + visual_clauses

        for i, clause in enumerate(all_clauses, 1):
            clause.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)
            clause.section_id = node.node_id or "UNKNOWN"
            clause.section_title = node.title
            if clause.page_number == 0:
                clause.page_number = node.start_index

        logger.info(
            f"Node '{node.title}' extraction complete: "
            f"text={len(text_clauses)} + visual={len(visual_clauses)} "
            f"= {len(all_clauses)} total"
        )

        for clause in all_clauses:
            source = "[image]" if "[图片内容]" in clause.original_text else "[text]"
            logger.debug(f"  {source} {clause.matrix_id}: {clause.original_text[:50]}...")

        # Attach clauses to the node (builds the clause tree)
        node.clauses = all_clauses

        return {"clauses": all_clauses}

    except Exception as e:
        logger.error(f"Node '{node.title}' extraction failed: {e}")
        logger.error(traceback.format_exc())
        return {"clauses": []}


# =========================================================================
# Content preparation
# =========================================================================

def _prepare_node_content(node: PageIndexNode) -> str:
    """
    Assemble node content for clause extraction.

    Returns the heading combined with ``original_text``, or an empty
    string if the node has no body text.
    """
    if node.original_text and node.original_text.strip():
        content = f"## {node.title}\n\n{node.original_text}"
        logger.debug(f"Using heading + original_text (length={len(content)})")
        return content

    logger.info(f"Node '{node.title}' has empty original_text – skipping extraction")
    return ""


# =========================================================================
# Prompt builder  (Chinese prompt – DO NOT translate)
# =========================================================================

def _build_extraction_prompt(node: PageIndexNode, content: str) -> str:
    """
    Build the clause-extraction prompt for the LLM.

    .. warning::
       The prompt text is in Chinese by design.  Translating it would
       alter LLM extraction behaviour.
    """
    prompt = f"""你是文档分析专家，专门从各类文档中提取可执行条款（Actionable Clauses）。

请分析以下章节内容，提取所有可执行条款，并对每个条款进行结构化分析。

**适用文档类型**：招标书、合同、合规制度、SOP、标准规范、政策文件、协议等各类文档。

## 章节信息
- 页码范围：{node.start_index}-{node.end_index}
- 节点ID：{node.node_id or "UNKNOWN"}

## 章节内容（标题+原文）
{content}

## 条款结构化提取（核心）

对每个条款进行以下7个维度的结构化分析：

### 1. type（条款类型）- **必填**
必须选择以下之一：
- **obligation**（义务）：必须做某事，如"甲方应提供..."、"乙方需确保..."
- **requirement**（需求）：对产品/服务的要求，如"系统需支持1000并发"、"响应时间不超过2秒"
- **prohibition**（禁止）：禁止做某事，如"不得转包"、"禁止使用..."
- **deliverable**（交付物）：需要交付的成果，如"需提交技术方案"、"需提供培训手册"
- **deadline**（截止时间）：时间节点要求，如"提交截止时间"、"交付期限"
- **penalty**（惩罚）：违约后果，如"逾期每天罚款..."、"不合格扣除保证金"
- **definition**（定义）：术语定义，如"本文档中的'系统'是指..."

### 2. actor（执行主体）- 选填
谁来执行这个条款：
- **party_a**（甲方）：文档中的第一方、委托方、采购方
- **party_b**（乙方）：文档中的第二方、承包方、供应方
- **provider**（提供方）：服务或产品提供者
- **client**（客户方）：接收服务或产品的一方
- **system**（系统）：软件系统、设备
- **organization**（组织）：项目组、监理方
- **role**（角色）：项目经理、技术负责人
- 其他具体角色名称

### 3. action（执行动作）- 选填
做什么动作：
- **submit**（提交）：提交文档、提交报告
- **provide**（提供）：提供服务、提供支持
- **ensure**（确保）：确保质量、确保安全
- **record**（记录）：记录日志、记录变更
- **comply**（遵守）：遵守规范、遵守标准
- **禁止**（如：不得、禁止、严禁）
- 其他动词

### 4. object（作用对象）- 选填
对什么产生作用：
- **document**（文档）：技术方案、报告文件
- **feature**（功能）：系统功能、业务功能
- **KPI**（指标）：性能指标、质量指标
- **material**（材料）：设备、软件、硬件
- 其他名词

### 5. condition（触发条件）- 选填
在什么条件下触发：
- **if**（如果）："如果验收不合格"、"如果出现故障"
- **when**（当）："当系统上线后"、"当合同签订后"
- **unless**（除非）："除非双方另有约定"
- 其他条件描述

### 6. deadline（时间要求）- 选填
时间限制：
- 具体日期："2024年12月31日前"
- 相对时间："合同签订后30天内"、"验收合格后15个工作日"
- 周期性："每月5日前"、"每季度末"

### 7. metric（量化指标）- 选填
可量化的标准：
- 数值："1000个并发用户"、"响应时间2秒"
- 范围："50-100万元"、"3-5年经验"
- 比较运算符：">= 500万"、"<= 10%"、"≥ 99.9%"

## 提取策略

**智能识别标题和原文**：
- 标题包含明确条款 → 从标题提取
- 标题仅是分类 → 从原文提取
- 标题和原文都有条款 → 分别提取

**识别表格来源**：
- 如果内容包含`【表格：images/xxx.jpg】`标记，填充`img_path`和`table_caption`字段

## 输出字段说明

每个条款必须包含以下字段：

### 必填字段：
- **type**：条款类型（obligation/requirement/prohibition/deliverable/deadline/penalty/definition）
- **original_text**：条款原文（从标题或原文中精确摘录）
- **page_number**：页码（使用 {node.start_index}）

### 结构化字段（尽量填写）：
- **actor**：执行主体（supplier/buyer/system/organization/role/其他）
- **action**：执行动作（submit/provide/ensure/record/comply/禁止.../其他动词）
- **object**：作用对象（document/feature/KPI/material/其他名词）
- **condition**：触发条件（if/when/unless等条件描述）
- **deadline**：时间要求（具体日期、相对时间、周期性要求）
- **metric**：量化指标（具体数值、范围、比较运算符）

### 辅助字段：
- **img_path**：图片/表格路径（如"images/xxx.jpg"）
- **image_caption**：图片描述（字符串）
- **table_caption**：表格标题（字符串）

## 提取原则

1. **完整性**：提取所有可执行条款，不遗漏
2. **准确性**：original_text必须精确摘录，不要改写
3. **结构化**：尽量填写所有7个结构化字段（type, actor, action, object, condition, deadline, metric）
4. **可执行性**：只提取明确的、可执行的条款，跳过描述性文字

## 输出格式
严格按照ClauseItem模型输出JSON列表。

## 示例说明

**示例1：需求类条款（requirement）**
```
## 系统需支持1000个并发用户，响应时间不超过2秒
```
提取为：
```json
{{{{
  "type": "requirement",
  "actor": "system",
  "action": "support",
  "object": "concurrent users",
  "condition": null,
  "deadline": null,
  "metric": "1000并发用户，响应时间≤2秒",
  "original_text": "系统需支持1000个并发用户，响应时间不超过2秒",
  "page_number": {node.start_index}
}}}}
```

**示例2：义务类条款（obligation）**
```
## 付款方式

合同签订后预付30%，验收合格后支付60%，质保期满支付尾款10%。
```
提取为：
```json
{{{{
  "type": "obligation",
  "actor": "buyer",
  "action": "pay",
  "object": "contract amount",
  "condition": "合同签订后、验收合格后、质保期满",
  "deadline": "分三期",
  "metric": "预付30%、验收60%、质保10%",
  "original_text": "合同签订后预付30%，验收合格后支付60%，质保期满支付尾款10%。",
  "page_number": {node.start_index}
}}}}
```

**示例3：交付物类条款（deliverable）**
```
乙方需提供技术方案、实施方案和培训计划各一份。
```
提取为：
```json
{{{{
  "type": "deliverable",
  "actor": "party_b",
  "action": "provide",
  "object": "technical documents",
  "condition": null,
  "deadline": null,
  "metric": "技术方案、实施方案、培训计划各一份",
  "original_text": "乙方需提供技术方案、实施方案和培训计划各一份。",
  "page_number": {node.start_index}
}}}}
```

**示例4：截止时间类条款（deadline）**
```
文件递交截止时间：2024年12月31日上午10:00（北京时间）
```
提取为：
```json
{{{{
  "type": "deadline",
  "actor": "party_b",
  "action": "submit",
  "object": "bidding documents",
  "condition": null,
  "deadline": "2024年12月31日上午10:00",
  "metric": null,
  "original_text": "投标文件递交截止时间：2024年12月31日上午10:00（北京时间）",
  "page_number": {node.start_index}
}}}}
```

**示例5：禁止类条款（prohibition）**
```
投标人不得转包或违法分包。
```
提取为：
```json
{{{{
  "type": "prohibition",
  "actor": "supplier",
  "action": "禁止",
  "object": "subcontracting",
  "condition": null,
  "deadline": null,
  "metric": null,
  "original_text": "投标人不得转包或违法分包。",
  "page_number": {node.start_index}
}}}}
```

**示例6：惩罚类条款（penalty）**
```
逾期交付的，每逾期一天，按合同总价的0.5%支付违约金。
```
提取为：
```json
{{{{
  "type": "penalty",
  "actor": "supplier",
  "action": "pay",
  "object": "penalty",
  "condition": "when 逾期交付",
  "deadline": null,
  "metric": "每天0.5%合同总价",
  "original_text": "逾期交付的，每逾期一天，按合同总价的0.5%支付违约金。",
  "page_number": {node.start_index}
}}}}
```

**示例7：表格条款（table）**
```
【表格：images/table_1.jpg】技术参数要求

参数名称 | 最低要求 | 评分标准
---------|----------|----------
CPU | 8核心 | 12核心满分
内存 | 16GB | 32GB满分
存储 | 500GB SSD | 1TB SSD满分
```
提取为（每行一个条款）：
```json
{{{{
  "type": "requirement",
  "actor": "system",
  "action": "meet",
  "object": "technical specifications",
  "condition": null,
  "deadline": null,
  "metric": "CPU≥8核心",
  "original_text": "CPU最低要求8核心",
  "page_number": {node.start_index},
  "img_path": "images/table_1.jpg",
  "table_caption": "技术参数要求"
}}}}
```

**重要提示**：
- 每个条款都必须填写type字段
- actor, action, object, condition, deadline, metric尽量填写，如果没有则填null
- original_text必须精确摘录原文
- **识别表格标记**：如果内容包含`【表格：images/xxx.jpg】`，必须将路径填充到`img_path`字段，表格标题填充到`table_caption`字段
- **表格条款逐行提取**：表格中的每一行数据可能是一个独立的条款，每个条款都要填充相同的`img_path`和`table_caption`
"""
    return prompt


# =========================================================================
# Image extraction helpers
# =========================================================================

def _extract_image_paths_from_markdown(
    content: str,
    mineru_output_dir: str,
) -> List[Tuple[str, str]]:
    """
    Find image references in Markdown and resolve to absolute paths.

    Args:
        content: Markdown text (may contain ``![alt](path)`` syntax).
        mineru_output_dir: Root directory of MinerU output.

    Returns:
        List of ``(absolute_path, relative_path)`` tuples for images
        that exist on disk.
    """
    matches = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", content)
    if not matches:
        return []

    tuples: List[Tuple[str, str]] = []
    base = Path(mineru_output_dir)

    for _description, rel_path in matches:
        abs_path = base / rel_path
        if abs_path.exists():
            tuples.append((str(abs_path), rel_path))
            logger.debug(f"Found image: {rel_path} -> {abs_path}")
        else:
            logger.warning(f"Image file missing: {abs_path}")

    return tuples


def _build_vision_prompt(node: PageIndexNode, rel_path: str) -> str:
    """Build the vision-extraction prompt for a single image."""
    return f"""你是文档分析专家。请分析这张图片内容，提取其中的可执行条款。

## 上下文信息
- 章节标题：{node.title}
- 页码范围：{node.start_index}-{node.end_index}
- 节点ID：{node.node_id or "UNKNOWN"}
- 当前图片：{rel_path}

## 任务说明
这张图片来自文档的"{node.title}"章节。请仔细分析图片中的内容：
- 如果是**表格**：提取表格中的可执行条款（义务、需求、交付物、时间等）
- 如果是**流程图/架构图**：提取系统架构要求、技术选型要求、部署要求等
- 如果是**截图/示例**：提取界面要求、功能要求、用户体验要求等
- 如果是**其他图示**：提取图片传达的关键条款信息

## 提取要求
1. **准确性**：只提取明确的条款，不要推测或添加图片中没有的内容
2. **完整性**：不要遗漏图片中的重要条款
3. **结构化**：对每个条款进行结构化分析（type, actor, action, object, condition, deadline, metric）
4. **来源标注**：original_text字段填写"[图片内容] "加上具体描述
5. **caption填充**：
   - 如果是图片（架构图/流程图/截图等），填充image_caption字段
   - 如果是表格，填充table_caption字段
   - caption应包含图片/表格的完整描述和关键信息

## 条款类型说明
- **obligation**（义务）：必须做某事
- **requirement**（需求）：对产品/服务的要求
- **prohibition**（禁止）：禁止做某事
- **deliverable**（交付物）：需要交付的成果
- **deadline**（截止时间）：时间节点要求
- **penalty**（惩罚）：违约后果
- **definition**（定义）：术语定义

## 输出格式
请以JSON数组格式输出条款列表，每个条款包含：
- type: 条款类型（必填）
- actor: 执行主体（选填）
- action: 执行动作（选填）
- object: 作用对象（选填）
- condition: 触发条件（选填）
- deadline: 时间要求（选填）
- metric: 量化指标（选填）
- original_text: "[图片内容] " + 图片中的具体描述
- page_number: {node.start_index}
- image_caption: 图片内容完整描述（仅当内容来自普通图片时填写）
- table_caption: 表格内容完整描述（仅当内容来自表格时填写）

如果图片中没有条款信息，返回空数组[]。
"""


def _process_single_image(
    abs_path: str,
    rel_path: str,
    node: PageIndexNode,
    llm_client: Any,
) -> List[ClauseItem]:
    """
    Extract clauses from a single image (thread-safe worker function).

    Returns:
        Clause list for this image, or empty list on failure.
    """
    try:
        prompt = _build_vision_prompt(node, rel_path)

        response_text = llm_client.vision_completion(
            text_prompt=prompt,
            image_inputs=[abs_path],
            temperature=0.2,
            max_tokens=4000,
        )

        json_match = re.search(r"\[[\s\S]*\]", response_text)
        if not json_match:
            logger.warning(
                f"Image {rel_path}: vision model response contains no JSON array"
            )
            return []

        items_data = json.loads(json_match.group())
        clauses: List[ClauseItem] = []

        for item in items_data:
            item.setdefault("section_id", node.node_id or "UNKNOWN")
            item.setdefault("section_title", node.title)
            item.setdefault("page_number", node.start_index)
            item.setdefault("type", "requirement")
            item["img_path"] = rel_path
            clauses.append(ClauseItem(**item))

        logger.info(f"  Image {rel_path}: extracted {len(clauses)} clause(s)")
        return clauses

    except json.JSONDecodeError as e:
        logger.error(f"Image {rel_path}: JSON parse error: {e}")
        return []
    except Exception as e:
        logger.error(f"Image {rel_path}: processing failed: {e}")
        return []


def _extract_clauses_from_images(
    image_paths: List[Tuple[str, str]],
    node: PageIndexNode,
    llm_client: Any,
    task_id: str | None = None,
) -> List[ClauseItem]:
    """
    Extract clauses from images **in parallel** using a thread pool.

    The vision model API calls are I/O-bound, so parallel execution via
    threads dramatically reduces wall-clock time (e.g. 5 images: ~50 s
    serial → ~10 s parallel).

    Args:
        image_paths: ``(absolute_path, relative_path)`` tuples.
        node: Parent document-tree node.
        llm_client: :class:`LLMClient` instance (thread-safe via httpx).
        task_id: For progress reporting.

    Returns:
        Clause list with ``img_path`` filled for each item.
    """
    if not image_paths:
        return []

    n_images = len(image_paths)
    logger.info(
        f"Node '{node.title}' has {n_images} image(s) – "
        "extracting clauses in parallel"
    )
    log_step(
        task_id,
        f"Starting parallel vision analysis for {n_images} image(s)",
    )

    # Cap parallelism: respect the configured limit (avoids rate-limit
    # pressure) and never use more workers than images.
    max_workers = min(settings.vision_max_workers, n_images)
    all_clauses: List[ClauseItem] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Submit all image tasks; use a dict to preserve order
        future_to_path = {
            pool.submit(
                _process_single_image, abs_path, rel_path, node, llm_client,
            ): (abs_path, rel_path)
            for abs_path, rel_path in image_paths
        }

        for future in as_completed(future_to_path):
            rel_path = future_to_path[future][1]
            completed += 1
            try:
                clauses = future.result()
                all_clauses.extend(clauses)
                log_step(
                    task_id,
                    f"Vision analysis {completed}/{n_images} done: "
                    f"{rel_path} ({len(clauses)} clauses)",
                )
            except Exception as e:
                logger.error(f"Image {rel_path}: unexpected future error: {e}")
                log_step(task_id, f"Vision analysis {completed}/{n_images} failed: {rel_path}")

    # Unified re-numbering across all images
    for i, clause in enumerate(all_clauses, 1):
        clause.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)

    logger.info(
        f"Extracted {len(all_clauses)} clause(s) from "
        f"{n_images} image(s) total (parallel, max_workers={max_workers})"
    )
    return all_clauses


# Backward-compatible alias
pageindex_enricher_node = clause_extractor_node
