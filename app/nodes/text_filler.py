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


def text_filler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Text Filler节点 - 为单个节点填充精确原文（并行版本）
    
    输入：
    - state["node"]: 单个PageIndexNode
    - state["pdf_path"]: PDF文件路径
    - state["pageindex_document"]: 完整文档（用于查找兄弟节点）
    
    输出：
    - 更新node的original_text和summary字段
    
    工作流程：
    1. 计算节点的页面范围（需要兄弟节点信息）
    2. 从PDF中提取这些页面的文本
    3. 调用LLM精确提取该节点标题下的内容
    4. 填充到节点的original_text字段
    """
    node = state.get("node")
    pdf_path = state.get("pdf_path")
    pageindex_doc = state.get("pageindex_document")
    task_id = state.get("task_id")
    
    if not node:
        logger.error("未找到node，无法填充原文")
        return {}
    
    if not pdf_path:
        logger.error("未找到pdf_path，无法提取PDF文本")
        return {}
    
    try:
        # 找到该节点的兄弟节点列表
        siblings = find_siblings(node, pageindex_doc)
        
        # 填充单个节点的原文（直接修改节点对象，无需返回）
        fill_single_node_text(
            node=node,
            pdf_path=pdf_path,
            siblings=siblings,
            task_id=task_id
        )
        
        # 不返回任何东西！节点已通过引用传递被修改
        return {}
        
    except Exception as e:
        logger.error(f"填充节点 '{node.title}' 的原文时出错: {e}")
        logger.exception(e)
        # 出错时确保字段完整性
        node.original_text = ""
        node.summary = ""
        return {}


def find_siblings(node: PageIndexNode, pageindex_doc: PageIndexDocument) -> List[PageIndexNode]:
    """
    在文档树中找到节点的兄弟节点列表
    
    Args:
        node: 目标节点
        pageindex_doc: 完整文档
        
    Returns:
        包含该节点的兄弟节点列表（包括节点自己）
    """
    def find_in_tree(current_list: List[PageIndexNode]) -> Optional[List[PageIndexNode]]:
        """递归查找节点所在的兄弟列表"""
        for n in current_list:
            if n is node:
                return current_list
            if n.nodes:
                result = find_in_tree(n.nodes)
                if result is not None:
                    return result
        return None
    
    # 从根节点开始查找
    siblings = find_in_tree(pageindex_doc.structure)
    if siblings is None:
        # 如果找不到，可能是根节点
        siblings = pageindex_doc.structure
    
    return siblings


def fill_single_node_text(
    node: PageIndexNode,
    pdf_path: str,
    siblings: List[PageIndexNode],
    task_id: Optional[str] = None
):
    """
    填充单个节点的原文（不递归）
    
    Args:
        node: 当前节点
        pdf_path: PDF文件路径
        siblings: 兄弟节点列表（包含自己）
        task_id: 任务ID
    """
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
        
        logger.debug(
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
                add_page_markers=True
            )
            
            logger.debug(f"   📥 PDF文本提取成功: 页面 [{start_page}, {end_page}]，文本长度: {len(page_text)}")
            
            if page_text and len(page_text) > 8:
                # 确定结束边界标题
                end_boundary_title = None
                if node.nodes:
                    end_boundary_title = node.nodes[0].title
                else:
                    next_sibling = node.find_next_sibling(siblings) if siblings else None
                    if next_sibling:
                        end_boundary_title = next_sibling.title
                
                # 调用LLM提取精确原文
                original_text = extract_original_text_with_llm(
                    node_title=node.title,
                    page_text=page_text,
                    end_boundary_title=end_boundary_title
                )
                print(f"上标题: {node.title}")
                print(f"正文: {original_text}")
                print(f"标题: {end_boundary_title}")
                # 记录LLM返回结果
                if original_text:
                    logger.debug(f"   ✅ LLM提取原文成功: 长度 {len(original_text)}")
                else:
                    logger.debug(f"   ⚠️ LLM返回空原文")
                
                # 填充到节点
                node.original_text = original_text if original_text else ""
                
                # 记录填充状态
                if original_text:
                    logger.debug(f"   ✅ 原文填充成功: 长度={len(original_text)}")
                else:
                    logger.debug(
                        f"   ℹ️  节点无正文内容: original_text已设为空字符串\n"
                        f"   节点: {node.title} (ID: {node.node_id})\n"
                        f"   这通常表示该节点只是章节标题，内容在子节点中"
                    )
                
                # 生成基于original_text的summary
                if original_text and len(original_text.strip()) > 0:
                    summary = generate_summary_from_text(
                        node_title=node.title,
                        original_text=original_text
                    )
                    node.summary = summary
                    logger.debug(f"   📝 Summary已生成，长度: {len(summary)}")
                else:
                    node.summary = ""
                    logger.debug(f"   📝 Summary设为空字符串（original_text为空）")
                
                logger.debug(f"   ✅ 原文填充完成\n")
            else:
                logger.warning(f"节点 '{node.title}' 的页面文本为空或过短，跳过填充")
                node.original_text = ""
                node.summary = ""
        else:
            logger.warning(
                f"节点 '{node.title}' 的页面范围无效: "
                f"[{start_page}, {end_page}]"
            )
            node.original_text = ""
            node.summary = ""
        
    except Exception as e:
        logger.error(f"填充节点 '{node.title}' 的原文时出错: {e}")
        logger.exception(e)
        node.original_text = ""
        node.summary = ""


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
            model=settings.text_filler_model,  # 使用text_filler专用模型
            temperature=0,  # 设为0，确保确定性输出，避免幻觉
            max_tokens=4000  # 限制输出长度
        )
        
        # 处理特殊情况
        if original_text:
            original_text = original_text.strip()
            # 识别特殊返回值标记
            if original_text in ["无内容", "未找到", "无", "TITLE_NOT_FOUND", "NO_CONTENT"]:
                logger.warning(
                    f"⚠️ LLM返回特殊标记: '{original_text}' (节点: {node_title})\n"
                    f"   这可能表示:\n"
                    f"   1. PDF文本中找不到该标题\n"
                    f"   2. 标题后没有内容\n"
                    f"   请检查PDF文本和标题匹配情况"
                )
                return ""
            
            # 记录成功提取
            logger.debug(f"✅ LLM成功提取原文: 长度={len(original_text)}, 节点={node_title}")
            return original_text
        else:
            logger.error(f"❌ LLM返回空响应 (节点: {node_title})")
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
            model=settings.summary_model,  # 使用summary专用模型
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
    构建精确原文提取的提示词（极简版 - 杜绝思考过程）
    
    Args:
        node_title: 当前节点标题（提取起始标记）
        page_text: PDF页面文本
        end_boundary_title: 结束边界标题（子节点或兄弟节点的标题，None表示提取到页面结束）
        
    Returns:
        提示词文本
    """
    if end_boundary_title:
        boundary_desc = f'在"{end_boundary_title}"标题之前停止'
    else:
        boundary_desc = '提取到文本结束'
    
    prompt = f"""逐字摘抄PDF文本中"{node_title}"标题之后的内容，{boundary_desc}。

【严格规则】
1. 直接输出纯文本，不要输出任何思考过程、分析、解释或步骤
2. 不要使用代码块、引号或任何格式标记
3. 逐字复制原文，一字不改，一字不加
4. 不包含标题本身，从标题后第一行开始
5. 保留原文换行
6. 如果找不到标题输出：TITLE_NOT_FOUND
7. 如果标题后无内容输出：NO_CONTENT

【示例】
PDF文本：
§2.1 安全要求
系统需支持SSL加密。
支持双因素认证。
§2.2 性能要求

提取"§2.1 安全要求"应输出：
系统需支持SSL加密。
支持双因素认证。

（直接输出以上两行，不要"正文："、"输出："等任何前缀或解释）

【PDF文本】
{page_text}

【立即输出摘抄结果】"""
    
    return prompt
