"""
需求原文匹配器 - RequirementTextMatcher

为需求的original_text在节点的content_list中查找对应的positions

核心特点：
1. 多级匹配策略（精确→相似度→子串→关键词）
2. 范围限制（只在节点的content_list中搜索）
3. 兼具精确性和灵活性
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from loguru import logger
from difflib import SequenceMatcher
import re


class RequirementTextMatcher:
    """需求原文匹配器"""
    
    # 匹配策略阈值
    SIMILARITY_THRESHOLD = 0.85  # 相似度匹配阈值
    KEYWORD_THRESHOLD = 0.70     # 关键词匹配阈值
    
    @staticmethod
    def find_requirement_positions(
        requirement_text: str,
        node_content_list: List[Dict[str, Any]],
        node_positions: List[List[int]]
    ) -> List[List[int]]:
        """
        在节点的content_list中查找需求原文对应的positions
        
        Args:
            requirement_text: 需求的original_text（LLM生成，可能有偏差）
            node_content_list: 节点对应的content列表（已通过positions筛选）
            node_positions: 节点的positions列表（用于验证）
        
        Returns:
            需求的positions列表，格式：[[page_idx, x1, y1, x2, y2], ...]
        """
        if not requirement_text or not node_content_list:
            return []
        
        logger.debug(f"开始匹配需求原文: {requirement_text[:50]}...")
        logger.debug(f"搜索范围: {len(node_content_list)} 个content节点")
        
        # 策略1：精确匹配（归一化后完全一致）
        positions = RequirementTextMatcher._exact_match(
            requirement_text, 
            node_content_list
        )
        if positions:
            logger.debug(f"✓ 策略1成功（精确匹配）: 找到 {len(positions)} 个位置")
            return positions
        
        # 策略2：相似度匹配（>=85%相似度）
        positions = RequirementTextMatcher._similarity_match(
            requirement_text, 
            node_content_list
        )
        if positions:
            logger.debug(f"✓ 策略2成功（相似度匹配）: 找到 {len(positions)} 个位置")
            return positions
        
        # 策略3：子串匹配（需求文本是节点文本的子串）
        positions = RequirementTextMatcher._substring_match(
            requirement_text, 
            node_content_list
        )
        if positions:
            logger.debug(f"✓ 策略3成功（子串匹配）: 找到 {len(positions)} 个位置")
            return positions
        
        # 策略4：关键词匹配（关键词匹配度>=70%）
        positions = RequirementTextMatcher._keyword_match(
            requirement_text, 
            node_content_list
        )
        if positions:
            logger.debug(f"✓ 策略4成功（关键词匹配）: 找到 {len(positions)} 个位置")
            return positions
        
        # 所有策略都失败
        logger.warning(f"✗ 所有匹配策略失败: {requirement_text[:50]}...")
        return []
    
    @staticmethod
    def _exact_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]]
    ) -> List[List[int]]:
        """
        策略1：精确匹配（归一化后完全一致）
        
        归一化规则：
        - 去除所有空白字符
        - 去除所有标点符号
        - 转小写
        
        支持类型：
        - type="text": 匹配text字段
        - type="list": 匹配list_items中的任一项
        """
        normalized_req = _normalize_text(requirement_text)
        
        for content in content_list:
            content_type = content.get("type")
            
            # 处理普通文本
            if content_type == "text":
                content_text = content.get("text", "")
                normalized_content = _normalize_text(content_text)
                
                if normalized_req == normalized_content:
                    logger.debug(f"精确匹配成功(text): '{content_text[:30]}...'")
                    return [_build_position(content)]
            
            # 处理列表
            elif content_type == "list":
                list_items = content.get("list_items", [])
                for item in list_items:
                    normalized_item = _normalize_text(item)
                    if normalized_req == normalized_item:
                        logger.debug(f"精确匹配成功(list): '{item[:30]}...'")
                        return [_build_position(content)]
        
        return []
    
    @staticmethod
    def _similarity_match(
        requirement_text: str, 
        content_list: List[Dict[str, Any]]
    ) -> List[List[int]]:
        """
        策略2：相似度匹配（>=85%相似度）
        
        使用difflib.SequenceMatcher计算相似度
        """
        normalized_req = _normalize_text(requirement_text)
        threshold = RequirementTextMatcher.SIMILARITY_THRESHOLD
        
        best_match = None
        best_score = 0.0
        
        for content in content_list:
            if content.get("type") != "text":
                continue
            
            content_text = content.get("text", "")
            normalized_content = _normalize_text(content_text)
            
            # 计算相似度
            score = SequenceMatcher(
                None, 
                normalized_req, 
                normalized_content
            ).ratio()
            
            if score > best_score:
                best_score = score
                best_match = content
        
        if best_score >= threshold:
            logger.debug(
                f"相似度匹配成功: score={best_score:.2f}, "
                f"text='{best_match.get('text', '')[:30]}...'"
            )
            return [_build_position(best_match)]
        
        return []
    
    @staticmethod
    def _substring_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]]
    ) -> List[List[int]]:
        """
        策略3：子串匹配（需求文本是内容的子串）
        
        适用场景：
        - LLM截取了部分原文
        - 原文较长，需求只引用了一部分
        
        支持类型：
        - type="text": 匹配text字段
        - type="list": 匹配list_items拼接后的文本
        """
        normalized_req = _normalize_text(requirement_text)
        
        # 拼接所有content的文本，并记录每个content的位置
        full_text = ""
        content_map = []  # [(start_pos, end_pos, content), ...]
        
        for content in content_list:
            content_type = content.get("type")
            
            # 处理普通文本
            if content_type == "text":
                text = _normalize_text(content.get("text", ""))
                start = len(full_text)
                full_text += text
                end = len(full_text)
                content_map.append((start, end, content))
            
            # 处理列表（拼接所有list_items）
            elif content_type == "list":
                list_items = content.get("list_items", [])
                combined_text = "".join([_normalize_text(item) for item in list_items])
                start = len(full_text)
                full_text += combined_text
                end = len(full_text)
                content_map.append((start, end, content))
        
        # 查找子串位置
        pos = full_text.find(normalized_req)
        if pos == -1:
            return []
        
        # 找到包含该子串的content（可能跨多个content）
        positions = []
        req_start = pos
        req_end = pos + len(normalized_req)
        
        for start, end, content in content_map:
            # 检查是否有重叠
            if not (end <= req_start or start >= req_end):
                positions.append(_build_position(content))
        
        if positions:
            logger.debug(
                f"子串匹配成功: 找到 {len(positions)} 个content节点, "
                f"子串位置=[{req_start}, {req_end}]"
            )
        
        return positions
    
    @staticmethod
    def _keyword_match(
        requirement_text: str,
        content_list: List[Dict[str, Any]]
    ) -> List[List[int]]:
        """
        策略4：关键词匹配（关键词匹配度>=70%）
        
        适用场景：
        - LLM改写了原文
        - 需求是原文的总结
        
        支持类型：
        - type="text": 匹配text字段
        - type="list": 匹配list_items拼接后的文本
        """
        # 提取关键词（去除停用词）
        req_keywords = _extract_keywords(requirement_text)
        
        if not req_keywords:
            return []
        
        threshold = RequirementTextMatcher.KEYWORD_THRESHOLD
        best_match = None
        best_score = 0.0
        best_text = ""
        
        for content in content_list:
            content_type = content.get("type")
            
            # 处理普通文本
            if content_type == "text":
                content_text = content.get("text", "")
                content_keywords = _extract_keywords(content_text)
                
                # 计算关键词匹配度
                matched = len(req_keywords & content_keywords)
                total = len(req_keywords)
                score = matched / total if total > 0 else 0.0
                
                if score > best_score:
                    best_score = score
                    best_match = content
                    best_text = content_text
            
            # 处理列表（拼接所有list_items）
            elif content_type == "list":
                list_items = content.get("list_items", [])
                combined_text = "".join(list_items)
                content_keywords = _extract_keywords(combined_text)
                
                # 计算关键词匹配度
                matched = len(req_keywords & content_keywords)
                total = len(req_keywords)
                score = matched / total if total > 0 else 0.0
                
                if score > best_score:
                    best_score = score
                    best_match = content
                    best_text = combined_text[:50]
        
        if best_score >= threshold:
            logger.debug(
                f"关键词匹配成功: score={best_score:.2f}, "
                f"text='{best_text[:30]}...'"
            )
            return [_build_position(best_match)]
        
        return []


# ============================================================================
# 辅助函数
# ============================================================================

def _normalize_text(text: str) -> str:
    """
    文本归一化（增强版）
    
    规则：
    1. 去除序号标记（（1）、1.、1）、①等）
    2. 去除所有空白字符（空格、换行、制表符等）
    3. 去除所有标点符号
    4. 转小写
    
    Args:
        text: 原始文本
    
    Returns:
        归一化后的文本
    """
    # 1. 去除常见序号标记（在文本开头）
    # 匹配：（1）、（一）、1.、1）、①、a)、A.等
    text = re.sub(r'^[\(（]\s*[0-9一二三四五六七八九十百千万零壹贰叁肆伍陆柒捌玖拾佰仟萬零]+\s*[\)）]', '', text)
    text = re.sub(r'^[0-9一二三四五六七八九十百千万零壹贰叁肆伍陆柒捌玖拾佰仟萬零]+\s*[.、。）\)]', '', text)
    text = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]', '', text)
    text = re.sub(r'^[a-zA-Z]\s*[\)）.]', '', text)
    
    # 2. 去除空白
    text = re.sub(r'\s+', '', text)
    
    # 3. 去除标点（保留字母数字和中文）
    text = re.sub(r'[^\w]', '', text)
    
    # 4. 转小写
    text = text.lower()
    
    return text


def _build_position(content: Dict[str, Any]) -> List[int]:
    """
    从content构建position
    
    Args:
        content: MinerU的content节点
    
    Returns:
        position: [page_idx, x1, y1, x2, y2]
    """
    page_idx = content.get("page_idx", 0)
    bbox = content.get("bbox", [0, 0, 0, 0])
    
    # 确保bbox是4个元素的列表
    if not isinstance(bbox, list) or len(bbox) != 4:
        logger.warning(f"无效的bbox: {bbox}")
        bbox = [0, 0, 0, 0]
    
    return [page_idx] + bbox


def _extract_keywords(text: str) -> Set[str]:
    """
    提取关键词（简单版：分词+去停用词）
    
    Args:
        text: 文本内容
    
    Returns:
        关键词集合
    """
    try:
        import jieba
        
        # 分词
        words = jieba.cut(text)
        
        # 简单停用词列表（可扩展）
        stopwords = {
            '的', '了', '是', '在', '和', '与', '等', '或', '及',
            '、', '，', '。', '：', '；', '？', '！', '"', '"',
            '需', '要', '应', '可', '能', '将', '为', '以', '从',
            '个', '项', '条', '款', '类', '种', '次', '中', '等等'
        }
        
        # 提取关键词（长度>1，不在停用词中）
        keywords = {
            w.strip() for w in words 
            if w.strip() and len(w.strip()) > 1 and w not in stopwords
        }
        
        return keywords
        
    except ImportError:
        # jieba未安装时的降级方案：简单分割
        logger.warning("jieba未安装，使用简单分词")
        words = re.findall(r'[\w]+', text)
        return {w for w in words if len(w) > 1}


# ============================================================================
# 工具函数：从完整content_list中提取节点对应的内容
# ============================================================================

def extract_node_content_list(
    node_positions: List[List[int]],
    full_content_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    从完整content_list中提取节点对应的内容
    
    Args:
        node_positions: 节点的positions列表 [[page_idx, x1, y1, x2, y2], ...]
        full_content_list: 完整的content_list
    
    Returns:
        节点对应的content列表
    """
    if not node_positions:
        logger.warning("node_positions为空，无法提取content")
        return []
    
    node_contents = []
    
    # 为每个position找到对应的content
    for pos in node_positions:
        if len(pos) < 5:
            logger.warning(f"无效的position: {pos}")
            continue
        
        page_idx = pos[0]
        bbox = pos[1:5]
        
        # 在content_list中查找匹配的content
        for content in full_content_list:
            if content.get("page_idx") == page_idx:
                content_bbox = content.get("bbox")
                if content_bbox and len(content_bbox) == 4:
                    # 比较bbox（允许小误差）
                    if _bbox_equal(content_bbox, bbox):
                        node_contents.append(content)
                        break
    
    logger.debug(
        f"从 {len(node_positions)} 个positions中提取到 "
        f"{len(node_contents)} 个content节点"
    )
    
    return node_contents


def _bbox_equal(bbox1: List[float], bbox2: List[int], tolerance: float = 0.1) -> bool:
    """
    比较两个bbox是否相等（允许小误差）
    
    Args:
        bbox1: 第一个bbox [x1, y1, x2, y2]
        bbox2: 第二个bbox [x1, y1, x2, y2]
        tolerance: 容差
    
    Returns:
        是否相等
    """
    if len(bbox1) != 4 or len(bbox2) != 4:
        return False
    
    for i in range(4):
        if abs(bbox1[i] - bbox2[i]) > tolerance:
            return False
    
    return True