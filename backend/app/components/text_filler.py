"""
Text Filler节点 - 精确原文填充（基于MinerU content_list）

使用MinerU解析的content_list为每个节点填充精确的原文内容
支持文本、列表、图片、表格等多种类型的内容
"""

from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
from app.domain.schema import DocumentAnalysisState, PageIndexNode, PageIndexDocument
from app.tools.section_slicer import (
    extract_content_by_title_range,
    extract_bbox_positions_with_titles,
    extract_content_between,
    extract_text_by_page_range,
)
from app.services.llm_client import get_llm_client
from app.services.task_tracker import TaskTracker
from app.domain.settings import settings
from app.tools.progress_helper import log_step


def text_filler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Text Filler节点 - 为单个节点填充精确原文（基于MinerU，并行版本）
    
    输入：
    - state["node"]: 单个PageIndexNode
    - state["pageindex_document"]: 完整文档（用于查找兄弟节点）
    - state["mineru_content_list"]: MinerU解析的内容列表
    - state["mineru_output_dir"]: MinerU输出目录
    
    输出：
    - 更新node的original_text和summary字段
    
    工作流程：
    1. 计算节点的页面范围（需要兄弟节点信息）
    2. 使用title_matcher从content_list中提取内容
    3. 填充到节点的original_text字段（包含图片、表格的Markdown格式）
    4. 生成summary
    """
    node = state.get("node")
    pageindex_doc = state.get("pageindex_document")
    mineru_content_list = state.get("mineru_content_list")
    mineru_output_dir = state.get("mineru_output_dir")
    task_id = state.get("task_id")
    
    if not node:
        logger.error("未找到node，无法填充原文")
        return {}
    
    if not mineru_content_list:
        logger.error("未找到mineru_content_list，无法提取内容")
        logger.warning("请确保MinerU解析节点已成功执行")
        return {}
    
    try:
        # 找到该节点的兄弟节点列表
        siblings = find_siblings(node, pageindex_doc)
        
        # 填充单个节点的原文（直接修改节点对象，无需返回）
        fill_single_node_text(
            node=node,
            pageindex_document=pageindex_doc,
            mineru_content_list=mineru_content_list,
            mineru_output_dir=mineru_output_dir,
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
    pageindex_document: PageIndexDocument,
    mineru_content_list: List[Dict[str, Any]],
    mineru_output_dir: str,
    siblings: List[PageIndexNode],
    task_id: Optional[str] = None
):
    """
    填充单个节点的原文（基于MinerU content_list）
    
    Args:
        node: 当前节点
        pageindex_document: 完整文档（用于查找父节点的兄弟）
        mineru_content_list: MinerU解析的内容列表
        mineru_output_dir: MinerU输出目录
        siblings: 兄弟节点列表（包含自己）
        task_id: 任务ID
    """
    try:
        # 1. 确定结束边界标题（现在title已包含完整序号）
        end_boundary_title = None
        if node.nodes:
            # 有子节点：边界是第一个子节点
            end_boundary_title = node.nodes[0].title
        else:
            # 叶子节点：先找直接兄弟
            next_sibling = node.find_next_sibling(siblings) if siblings else None
            if next_sibling:
                end_boundary_title = next_sibling.title
            else:
                # 没有直接兄弟：向上查找父节点的兄弟
                end_boundary_title = _find_parent_sibling_title(node, pageindex_document)
        
        # 2. 计算当前节点的页面范围
        start_page, end_page = calculate_text_fill_range(node, siblings)
        
        # 判断节点类型（用于日志）
        node_type = "有子节点" if node.nodes else "叶子节点"
        boundary_info = f"边界='{end_boundary_title}'" if end_boundary_title else "边界=节点结束页"
        
        logger.info(
            f"📄 节点 '{node.title}' (ID: {node.node_id})\n"
            f"   类型: {node_type}\n"
            f"   页面范围（PageIndex, 1-based）: [{start_page}, {end_page}]\n"
            f"   {boundary_info}"
        )
        
        # 2. 动态扩展页面范围
        boundary_page_idx = None
        if end_boundary_title:
            # 尝试在content_list中查找边界标题
            boundary_page_idx = _find_title_page_idx(end_boundary_title, mineru_content_list)
        
        if boundary_page_idx is not None:
            # 情况A：边界标题存在于content_list - 扩展到包含边界标题页
            boundary_page_1based = boundary_page_idx + 1
            if boundary_page_1based > end_page:
                logger.debug(
                    f"   📍 扩展页面范围以包含边界标题:\n"
                    f"      边界标题: '{end_boundary_title}'\n"
                    f"      原范围: [{start_page}, {end_page}]\n"
                    f"      新范围: [{start_page}, {boundary_page_1based}]"
                )
                end_page = boundary_page_1based
        else:
            # 情况B：无边界标题 或 边界标题在content_list中找不到
            # → 扩展到文档真实结尾
            doc_last_page = _get_document_last_page(mineru_content_list)
            if doc_last_page is not None:
                doc_last_page_1based = doc_last_page + 1
                if doc_last_page_1based > end_page:
                    if end_boundary_title:
                        logger.debug(
                            f"   ⚠️  边界标题在content_list中未找到，扩展到文档结尾:\n"
                            f"      边界标题: '{end_boundary_title}'\n"
                            f"      原范围: [{start_page}, {end_page}]\n"
                            f"      文档实际结尾: 第{doc_last_page_1based}页\n"
                            f"      新范围: [{start_page}, {doc_last_page_1based}]"
                        )
                    else:
                        logger.debug(
                            f"   📄 扩展到文档结尾:\n"
                            f"      这是文档最后节点\n"
                            f"      原范围: [{start_page}, {end_page}]\n"
                            f"      文档实际结尾: 第{doc_last_page_1based}页\n"
                            f"      新范围: [{start_page}, {doc_last_page_1based}]"
                        )
                    end_page = doc_last_page_1based
        
        # 3. 如果页面范围有效，使用title_matcher提取内容
        if start_page <= end_page and end_page > 0:
            # 【关键转换】PageIndex是1-based，MinerU是0-based
            # PageIndex的start_index=3表示PDF第3页
            # MinerU的page_idx=2表示PDF第3页
            mineru_start_page = start_page - 1
            mineru_end_page = end_page - 1
            
            logger.info(
                f"   ✓ 索引转换完成:\n"
                f"     PageIndex (1-based): [{start_page}, {end_page}]\n"
                f"     MinerU (0-based):    [{mineru_start_page}, {mineru_end_page}]\n"
                f"     对应PDF页码: 第{start_page}页到第{end_page}页"
            )
            
            # 使用鲁棒的多策略标题匹配（级联 fallback）
            from app.tools.section_slicer import TitleMatcher, extract_bbox_positions
            
            # 1. 使用鲁棒方法找到起始标题的索引（5 级策略级联）
            start_idx = TitleMatcher.find_title_in_content_list_robust(
                node.title,
                mineru_content_list,
                (mineru_start_page, mineru_end_page)
            )
            
            if start_idx is not None:
                # 2. 确定有效页面范围（如果标题在扩展范围中找到，需扩大切片范围）
                found_page = mineru_content_list[start_idx].get("page_idx", mineru_start_page)
                effective_start = min(mineru_start_page, found_page)
                effective_end = max(mineru_end_page, found_page + 3)
                
                # 3. 基于已知 start_idx 直接提取内容（避免重复搜索起始标题）
                contents = extract_content_between(
                    start_idx=start_idx,
                    end_title=end_boundary_title,
                    content_list=mineru_content_list,
                    page_range=(effective_start, effective_end)
                )
                original_text = TitleMatcher.extract_text_from_contents(contents)
                
                # 4. 提取 positions（包含起始标题的 bbox）
                start_content = mineru_content_list[start_idx]
                contents_with_title = [start_content] + contents
                positions = extract_bbox_positions(contents_with_title)
            else:
                # 所有标题匹配策略均失败 → 页面范围兜底提取
                logger.warning(
                    f"节点 '{node.title}' 的标题在content_list中未找到"
                    f"（5级鲁棒策略均失败），使用页面范围文本提取作为fallback"
                )
                fallback_text, fallback_contents = extract_text_by_page_range(
                    mineru_content_list, mineru_start_page, mineru_end_page
                )
                original_text = fallback_text
                positions = extract_bbox_positions(fallback_contents)
            
            # 填充到节点
            node.original_text = original_text if original_text else ""
            node.positions = positions if positions else []
            
            # 记录填充状态
            if original_text and len(original_text.strip()) > 0:
                logger.debug(f"   ✅ 原文提取成功: 长度={len(original_text)}")
                logger.debug(f"   📍 坐标提取成功: {len(positions)} 个bbox")
                
                # 统计内容类型（检查是否包含图片/表格）
                has_images = "![" in original_text
                if has_images:
                    image_count = original_text.count("![")
                    logger.debug(f"   📷 包含 {image_count} 个图片/表格（Markdown格式）")
                
                # 生成summary
                summary = generate_summary_from_text(
                    node_title=node.title,
                    original_text=original_text
                )
                node.summary = summary
                logger.debug(f"   📝 Summary已生成，长度: {len(summary)}")
            else:
                # 即使没有正文内容，也要保留标题的bbox坐标
                logger.debug(
                    f"   ℹ️  节点无正文内容: original_text已设为空字符串\n"
                    f"   节点: {node.title} (ID: {node.node_id})\n"
                    f"   📍 但保留了标题bbox: {len(positions)} 个坐标\n"
                    f"   可能原因: 1) 标题下确实无内容 2) 内容在子节点中"
                )
                node.summary = ""
                # 不要清空positions！保留标题的bbox
            
            logger.debug(f"   ✅ 原文填充完成\n")
        else:
            logger.warning(
                f"节点 '{node.title}' 的页面范围无效: "
                f"[{start_page}, {end_page}]"
            )
            node.original_text = ""
            node.summary = ""
            node.positions = []
        
    except Exception as e:
        logger.error(f"填充节点 '{node.title}' 的原文时出错: {e}")
        logger.exception(e)
        node.original_text = ""
        node.summary = ""
        node.positions = []


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
        llm_service = get_llm_client()
        
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
            model=settings.summarizer_llm_name,  # summarizer-specific model
            temperature=0.3,
            max_tokens=1000
        )
        
        return summary.strip() if summary else ""
        
    except Exception as e:
        logger.error(f"生成summary时出错: {e}")
        # 降级：使用原文前500字作为摘要
        return original_text[:500] + "..." if len(original_text) > 500 else original_text


def _find_title_page_idx(
    target_title: str,
    content_list: List[Dict[str, Any]]
) -> Optional[int]:
    """
    在content_list中查找标题所在的页码（page_idx，0-based）
    
    Args:
        target_title: 目标标题
        content_list: MinerU解析的内容列表
        
    Returns:
        找到的page_idx（0-based），未找到返回None
    """
    from app.tools.section_slicer import TitleMatcher
    
    # 使用鲁棒方法查找标题（无页面范围限制时本质上只有策略1生效，
    # 但保持一致性，且 light normalization 策略仍可提供额外匹配能力）
    title_idx = TitleMatcher.find_title_in_content_list_robust(
        target_title,
        content_list,
        page_range=None  # 不限制页面范围
    )
    
    if title_idx is not None:
        # 返回该content的page_idx
        return content_list[title_idx].get("page_idx")
    return None


def _find_parent_sibling_title(
    node: PageIndexNode,
    pageindex_document: PageIndexDocument
) -> Optional[str]:
    """
    递归向上查找父/祖先节点的下一个兄弟作为边界标题
    
    查找策略：
    1. 查找父节点的下一个兄弟
    2. 如果父节点没有兄弟，继续向上查找祖父节点的兄弟
    3. 递归向上，直到找到或到达根节点
    4. 如果到根节点还没找到，返回None（表示是文档的最后节点）
    
    Args:
        node: 当前节点
        pageindex_document: 完整文档
        
    Returns:
        找到的祖先兄弟标题，未找到返回None（表示到文档结尾）
    """
    def find_node_path(
        target: PageIndexNode,
        current_list: List[PageIndexNode],
        path: List[Tuple[PageIndexNode, List[PageIndexNode]]]
    ) -> Optional[List[Tuple[PageIndexNode, List[PageIndexNode]]]]:
        """
        递归查找节点的完整路径
        
        Returns:
            路径列表，每个元素是(节点, 该节点的兄弟列表)
        """
        for i, n in enumerate(current_list):
            if n is target:
                # 找到目标节点
                path.append((n, current_list))
                return path
            if n.nodes:
                # 记录当前节点及其兄弟列表
                new_path = path + [(n, current_list)]
                # 递归查找子节点
                result = find_node_path(target, n.nodes, new_path)
                if result:
                    return result
        return None
    
    # 1. 找到从根到目标节点的完整路径
    path = find_node_path(node, pageindex_document.structure, [])
    
    if not path:
        return None
    
    # 2. 从路径倒序遍历（从目标节点向上到根节点的父节点）
    # path[-1] 是目标节点本身，path[-2]是父节点，path[-3]是祖父节点...
    # 注意：range要从len(path)-1到0（包含），这样才能检查所有层级的兄弟
    for i in range(len(path) - 1, -1, -1):
        current_node, siblings = path[i]
        
        # 在兄弟列表中找到当前节点的下一个兄弟
        try:
            current_idx = siblings.index(current_node)
            if current_idx < len(siblings) - 1:
                # 找到下一个兄弟
                next_sibling = siblings[current_idx + 1]
                logger.debug(
                    f"   ⬆️  向上查找边界:\n"
                    f"      当前节点: {node.title}\n"
                    f"      查找层级: 向上{len(path) - 1 - i}层\n"
                    f"      找到边界: {next_sibling.title}"
                )
                return next_sibling.title
        except ValueError:
            continue
    
    # 3. 如果递归到根节点还没找到，说明是文档最后的节点
    logger.debug(
        f"   📄 节点 '{node.title}' 是文档的最后节点\n"
        f"      将提取到文档结尾"
    )
    return None


def _get_document_last_page(content_list: List[Dict[str, Any]]) -> Optional[int]:
    """
    获取文档的最后一页页码（page_idx，0-based）
    
    Args:
        content_list: MinerU解析的内容列表
        
    Returns:
        最后一页的page_idx（0-based），未找到返回None
    """
    if not content_list:
        return None
    
    # 找到content_list中最大的page_idx
    max_page_idx = -1
    for content in content_list:
        page_idx = content.get("page_idx", -1)
        if page_idx > max_page_idx:
            max_page_idx = page_idx
    
    return max_page_idx if max_page_idx >= 0 else None



