"""
Text Filler节点 - 精确原文填充

递归遍历PageIndex结构树，为每个节点填充精确的原文内容（行级别）
"""

from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
from app.core.states import TenderAnalysisState, PageIndexNode, PageIndexDocument
from app.services.pdf_text_extractor import extract_pages_text
from app.services.llm_service import get_llm_service
from app.api.async_tasks import TaskManager
from app.core.config import settings


def text_filler_node(state: TenderAnalysisState) -> Dict[str, Any]:
    """
    Text Filler节点 - 为PageIndex结构树填充精确原文
    
    输入：
    - state.pageindex_document: PageIndex生成的结构树
    - state.pdf_path: PDF文件路径
    
    输出：
    - state.pageindex_document: 每个节点都包含original_text字段
    
    工作流程：
    1. 递归遍历整个结构树
    2. 对每个节点，根据其类型（有子/无子）计算应参照的页面范围
    3. 从PDF中提取这些页面的文本
    4. 调用LLM精确提取该节点标题下的内容
    5. 填充到节点的original_text字段
    """
    logger.info("=" * 60)
    logger.info("Text Filler节点开始执行")
    logger.info("=" * 60)
    
    pdf_path = state["pdf_path"]
    pageindex_doc = state.get("pageindex_document")
    task_id = state.get("task_id")
    
    if not pageindex_doc:
        logger.error("未找到pageindex_document，无法填充原文")
        return {"error_message": "未找到pageindex_document"}
    
    if not pdf_path:
        logger.error("未找到pdf_path，无法提取PDF文本")
        return {"error_message": "未找到pdf_path"}
    
    # 更新任务进度
    if task_id:
        TaskManager.log_progress(
            task_id,
            "正在填充精确原文...",
            35
        )
    
    try:
        # 递归填充所有节点的原文
        total_nodes = 0
        for root_node in pageindex_doc.structure:
            total_nodes += len(root_node.get_all_nodes())
        
        logger.info(f"开始为 {total_nodes} 个节点填充原文")
        
        filled_count = 0
        for i, root_node in enumerate(pageindex_doc.structure):
            logger.info(f"处理根节点 {i+1}/{len(pageindex_doc.structure)}: {root_node.title}")
            filled_count += fill_text_recursively(
                node=root_node,
                pdf_path=pdf_path,
                parent=None,
                siblings=pageindex_doc.structure,
                task_id=task_id
            )
        
        logger.info(f"✓ 原文填充完成，共填充 {filled_count} 个节点")
        
        # 更新任务进度
        if task_id:
            TaskManager.log_progress(
                task_id,
                f"✓ 原文填充完成，共填充 {filled_count} 个节点",
                45
            )
        
        return {
            "pageindex_document": pageindex_doc
        }
        
    except Exception as e:
        error_msg = f"原文填充失败: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)
        
        if task_id:
            TaskManager.log_progress(
                task_id,
                f"✗ {error_msg}",
                0
            )
        
        return {
            "error_message": error_msg
        }


def fill_text_recursively(
    node: PageIndexNode,
    pdf_path: str,
    parent: Optional[PageIndexNode] = None,
    siblings: Optional[List[PageIndexNode]] = None,
    task_id: Optional[str] = None
) -> int:
    """
    递归填充节点的原文
    
    Args:
        node: 当前节点
        pdf_path: PDF文件路径
        parent: 父节点
        siblings: 兄弟节点列表（包含自己）
        task_id: 任务ID
        
    Returns:
        填充的节点数量
    """
    filled_count = 0
    
    try:
        # 1. 计算当前节点的页面范围
        start_page, end_page = calculate_text_fill_range(node, siblings)
        
        # 判断节点类型
        node_type = "有子节点" if node.nodes else "叶子节点"
        boundary_info = ""
        if node.nodes:
            boundary_info = f"边界=第一个子节点 '{node.nodes[0].title}'"
        else:
            next_sibling = node.find_next_sibling(siblings) if siblings else None
            if next_sibling:
                boundary_info = f"边界=下一个兄弟 '{next_sibling.title}'"
            else:
                boundary_info = "边界=节点结束页"
        
        logger.info(
            f"📄 节点 '{node.title}' (ID: {node.node_id})\n"
            f"   类型: {node_type}\n"
            f"   页面范围: [{start_page}, {end_page}]\n"
            f"   {boundary_info}"
        )
        
        # 2. 如果页面范围有效，提取PDF文本并填充原文
        if start_page <= end_page and end_page > 0:
            # 提取PDF文本
            page_text = extract_pages_text(
                pdf_path, 
                start_page, 
                end_page,
                add_page_markers=True  # 添加页码标记
            )
            
            logger.debug(f"   📥 PDF文本提取成功: 页面 [{start_page}, {end_page}]，文本长度: {len(page_text)}")
            
            if page_text and len(page_text) > 20:
                # 确定结束边界标题
                end_boundary_title = None
                if node.nodes:
                    # 有子节点，结束边界是第一个子节点的标题
                    end_boundary_title = node.nodes[0].title
                else:
                    # 叶子节点，结束边界是下一个兄弟节点的标题
                    next_sibling = node.find_next_sibling(siblings) if siblings else None
                    if next_sibling:
                        end_boundary_title = next_sibling.title
                
                # 调用LLM提取精确原文，提供边界信息
                original_text = extract_original_text_with_llm(
                    node_title=node.title,
                    page_text=page_text,
                    end_boundary_title=end_boundary_title
                )
                
                # 记录LLM返回结果
                if original_text:
                    logger.info(f"   ✅ LLM提取原文成功: 长度 {len(original_text)}")
                else:
                    logger.warning(f"   ⚠️ LLM返回空原文")
                
                # 填充到节点（即使为空也填充，保持一致性）
                node.original_text = original_text if original_text else ""
                
                # 生成基于original_text的summary（只要有原文就生成，不限制长度）
                if original_text and len(original_text.strip()) > 0:
                    summary = generate_summary_from_text(
                        node_title=node.title,
                        original_text=original_text
                    )
                    node.summary = summary
                    logger.debug(f"   📝 Summary已生成，长度: {len(summary)}")
                
                filled_count += 1
                
                logger.info(f"   ✅ 原文填充完成\n")
            else:
                logger.warning(f"节点 '{node.title}' 的页面文本为空或过短，跳过填充")
                node.original_text = ""
        else:
            logger.warning(
                f"节点 '{node.title}' 的页面范围无效: "
                f"[{start_page}, {end_page}]"
            )
            node.original_text = ""
        
        # 3. 递归处理子节点
        if node.nodes:
            for child in node.nodes:
                filled_count += fill_text_recursively(
                    node=child,
                    pdf_path=pdf_path,
                    parent=node,
                    siblings=node.nodes,
                    task_id=task_id
                )
        
        return filled_count
        
    except Exception as e:
        logger.error(f"填充节点 '{node.title}' 的原文时出错: {e}")
        logger.exception(e)
        node.original_text = ""
        return filled_count


def calculate_text_fill_range(
    node: PageIndexNode,
    siblings: Optional[List[PageIndexNode]] = None
) -> Tuple[int, int]:
    """
    计算节点应该填充的文本所对应的PDF页面范围
    
    规则（修正）：
    1. 有子节点：[node.start_index, first_child.start_index]
       - 提取到包含第一个子节点标题的页面，让LLM识别边界
    2. 叶子节点+有兄弟：[node.start_index, next_sibling.start_index]
       - 提取到包含下一个兄弟标题的页面，让LLM识别边界
    3. 叶子节点+无兄弟：[node.start_index, node.end_index]
       - 提取到节点的结束页
    
    核心理念：必须包含边界标题所在页，让LLM在文本中识别边界并停止
    
    Args:
        node: 当前节点
        siblings: 兄弟节点列表（包含当前节点）
        
    Returns:
        (start_page, end_page) 1-based, 闭区间
    """
    start_page = node.start_index
    
    if node.nodes:  # 有子节点
        # 结束页 = 第一个子节点的开始页（包含边界标题）
        end_page = node.nodes[0].start_index
    else:  # 叶子节点
        # 找下一个兄弟
        next_sibling = node.find_next_sibling(siblings) if siblings else None
        
        if next_sibling:
            # 结束页 = 下一个兄弟的开始页（包含边界标题）
            end_page = next_sibling.start_index
        else:
            # 没有下一个兄弟，使用自己的结束页
            end_page = node.end_index
    
    # 确保页面范围有效
    if end_page < start_page:
        logger.warning(
            f"节点 '{node.title}' 计算的结束页 ({end_page}) "
            f"小于开始页 ({start_page})，强制使用开始页"
        )
        end_page = start_page
    
    return (start_page, end_page)


def extract_original_text_with_llm(
    node_title: str,
    page_text: str,
    end_boundary_title: Optional[str] = None
) -> str:
    """
    使用LLM从页面文本中提取节点的精确原文
    
    Args:
        node_title: 当前节点标题（提取起始标记）
        page_text: PDF页面文本
        end_boundary_title: 结束边界标题（子节点或兄弟节点的标题）
        
    Returns:
        提取的原文内容
    """
    try:
        # 构建提示词
        prompt = build_text_extraction_prompt(node_title, page_text, end_boundary_title)
        
        # 调用LLM
        llm_service = get_llm_service()
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的文档内容提取专家，擅长从PDF文本中精确提取指定标题下的内容。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # 使用text_completion方法生成文本
        # temperature=0确保精确摘录，不产生幻觉
        original_text = llm_service.text_completion(
            messages=messages,
            temperature=0,  # 设为0，确保确定性输出，避免幻觉
            max_tokens=4000  # 限制输出长度
        )
        
        # 处理特殊情况
        if original_text:
            original_text = original_text.strip()
            # 识别特殊返回值标记
            if original_text in ["无内容", "未找到", "无", "TITLE_NOT_FOUND", "NO_CONTENT"]:
                logger.info(f"LLM返回特殊标记: {original_text}，转换为空字符串")
                return ""
            return original_text
        else:
            logger.warning(f"LLM未返回有效响应")
            return ""
        
    except Exception as e:
        logger.error(f"使用LLM提取原文时出错: {e}")
        logger.exception(e)
        return ""


def generate_summary_from_text(
    node_title: str,
    original_text: str,
    max_length: int = 500
) -> str:
    """
    基于精确原文生成摘要
    
    Args:
        node_title: 节点标题
        original_text: 精确提取的原文
        max_length: 摘要最大长度
        
    Returns:
        生成的摘要
    """
    try:
        llm_service = get_llm_service()
        
        prompt = f"""请为以下章节内容生成一个简明扼要的摘要。

**章节标题**：{node_title}

**章节原文**：
{original_text}

**要求**：
1. 摘要应简洁明了，长度控制在{max_length}字以内
2. 提炼核心要点，保留关键信息
3. 使用客观、专业的语言
4. 直接输出摘要内容，不要添加"摘要："等前缀

**输出摘要**："""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的文档摘要专家，擅长提炼文本的核心内容。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        summary = llm_service.text_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=1000
        )
        
        return summary.strip() if summary else ""
        
    except Exception as e:
        logger.error(f"生成summary时出错: {e}")
        # 降级：使用原文前500字作为摘要
        return original_text[:500] + "..." if len(original_text) > 500 else original_text


def build_text_extraction_prompt(
    node_title: str,
    page_text: str,
    end_boundary_title: Optional[str] = None
) -> str:
    """
    构建精确原文提取的提示词（强化版 - 减少幻觉）
    
    Args:
        node_title: 当前节点标题（提取起始标记）
        page_text: PDF页面文本
        end_boundary_title: 结束边界标题（子节点或兄弟节点的标题，None表示提取到页面结束）
        
    Returns:
        提示词文本
    """
    if end_boundary_title:
        task_desc = f'"{node_title}"标题之后、"{end_boundary_title}"标题之前'
        boundary_instruction = f'一旦看到"{end_boundary_title}"，立即停止'
    else:
        task_desc = f'"{node_title}"标题之后到页面结束'
        boundary_instruction = '提取到页面结束或下一个标题前'
    
    prompt = f"""你是一个精确的文本摘录员。请从PDF文本中逐字摘录{task_desc}的内容。

⚠️ **极其重要的规则**：
1. 你的任务是**摘录**，不是总结、不是改写、不是扩展
2. 必须**逐字复制**原文，一个字都不能改，一个字都不能加
3. 只摘录存在的内容，绝对不要添加任何解释、说明或你自己的理解
4. 如果内容很短（只有几个字），那就只输出这几个字，不要试图扩展
5. 保持原文的换行和格式

🔍 **操作步骤**：
1. 在下面的文本中找到"{node_title}"标题
2. 从标题**之后的第一行**开始复制
3. {boundary_instruction}
4. 不包含标题本身

❌ **特殊情况**：
- 找不到标题 → 只输出：TITLE_NOT_FOUND
- 标题后无内容 → 只输出：NO_CONTENT

✅ **正确示例**：
PDF文本：
```
§2.1 安全要求
系统需支持SSL加密。
§2.2 性能要求
```
提取"§2.1 安全要求"应输出：
```
系统需支持SSL加密。
```
（只有这一句，不要加任何解释）

📄 **待摘录的PDF文本**：
```
{page_text}
```

🎯 **开始逐字摘录**（不要添加"原文："等前缀）："""
    
    return prompt
