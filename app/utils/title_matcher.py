"""
标题模糊匹配工具

用于在MinerU解析的content中查找PageIndex的标题，支持：
1. 格式差异（空格、标点）
2. 子标题包含父标题
3. 模糊匹配
"""

import re
from typing import Optional, List, Tuple, Dict, Any
from difflib import SequenceMatcher


class TitleMatcher:
    """标题模糊匹配器"""
    
    @staticmethod
    def normalize_title(title: str) -> str:
        """
        标题归一化处理
        
        Args:
            title: 原始标题
            
        Returns:
            归一化后的标题（去除空格、标点、转小写）
        """
        if not title:
            return ""
        
        # 1. 转小写
        normalized = title.lower()
        
        # 2. 去除所有空白字符
        normalized = re.sub(r'\s+', '', normalized)
        
        # 3. 去除常见标点符号（保留中文字符、数字、英文）
        # 但保留 § 这种特殊符号，因为它是标题的一部分
        normalized = re.sub(r'[.,;:!?。，；：！？、（）()【】\[\]{}""''\'""]', '', normalized)
        
        return normalized
    
    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """
        计算两个字符串的相似度（0-1）
        
        Args:
            str1: 字符串1
            str2: 字符串2
            
        Returns:
            相似度分数（0-1）
        """
        if not str1 or not str2:
            return 0.0
        
        return SequenceMatcher(None, str1, str2).ratio()
    
    @staticmethod
    def is_title_contained(
        target_title: str,
        content_text: str,
        similarity_threshold: float = 0.85
    ) -> bool:
        """
        判断目标标题是否包含在content文本中
        
        Args:
            target_title: 目标标题（PageIndex的标题）
            content_text: content的文本内容
            similarity_threshold: 相似度阈值
            
        Returns:
            是否匹配
        """
        # 归一化
        norm_target = TitleMatcher.normalize_title(target_title)
        norm_content = TitleMatcher.normalize_title(content_text)
        
        if not norm_target or not norm_content:
            return False
        
        # 1. 精确包含检查
        if norm_target in norm_content:
            return True
        
        # 2. 模糊匹配检查
        # 如果content包含target的大部分内容，也认为匹配
        if len(norm_target) <= len(norm_content):
            # 计算目标标题与content的相似度
            similarity = TitleMatcher.calculate_similarity(norm_target, norm_content[:len(norm_target) + 10])
            if similarity >= similarity_threshold:
                return True
        
        return False
    
    @staticmethod
    def find_title_in_content_list(
        target_title: str,
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None,
        similarity_threshold: float = 0.85
    ) -> Optional[int]:
        """
        在content_list中查找目标标题的索引
        
        Args:
            target_title: 目标标题（PageIndex的标题）
            content_list: MinerU解析的content列表
            page_range: 页面范围（page_idx, start, end），可选
            similarity_threshold: 相似度阈值
            
        Returns:
            找到的content索引，未找到返回None
        """
        norm_target = TitleMatcher.normalize_title(target_title)
        
        for i, content in enumerate(content_list):
            # 1. 检查页面范围
            if page_range:
                page_idx = content.get("page_idx", -1)
                if not (page_range[0] <= page_idx <= page_range[1]):
                    continue
            
            # 2. 提取content文本
            content_text = TitleMatcher._extract_content_text(content)
            if not content_text:
                continue
            
            # 3. 检查是否匹配
            if TitleMatcher.is_title_contained(target_title, content_text, similarity_threshold):
                return i
        
        return None
    
    @staticmethod
    def _extract_content_text(content: Dict[str, Any]) -> str:
        """
        从content中提取文本用于匹配
        
        Args:
            content: MinerU的content项
            
        Returns:
            提取的文本
        """
        content_type = content.get("type", "")
        
        if content_type == "text":
            return content.get("text", "")
        
        elif content_type == "list":
            # list类型：拼接所有list_items
            list_items = content.get("list_items", [])
            return " ".join(list_items)
        
        elif content_type == "image":
            # image类型：使用caption（如果有）
            caption = content.get("image_caption", [])
            if caption:
                return " ".join(caption)
            return ""
        
        elif content_type == "table":
            # table类型：使用caption（如果有）
            caption = content.get("table_caption", [])
            if caption:
                return " ".join(caption)
            return ""
        
        return ""
    
    @staticmethod
    def find_content_range_by_titles(
        start_title: str,
        end_title: Optional[str],
        content_list: List[Dict[str, Any]],
        page_range: Optional[Tuple[int, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据起始和结束标题，在content_list中查找内容范围
        
        Args:
            start_title: 起始标题（当前节点标题）
            end_title: 结束标题（下一个兄弟或子节点标题），None表示到页面结束
            content_list: MinerU解析的content列表
            page_range: 页面范围（start_page, end_page）
            
        Returns:
            范围内的content列表（不包含起始和结束标题本身）
        """
        # 1. 查找起始标题
        start_idx = TitleMatcher.find_title_in_content_list(
            start_title,
            content_list,
            page_range
        )
        
        if start_idx is None:
            # 找不到起始标题，返回空列表
            return []
        
        # 2. 确定结束索引
        if end_title:
            # 查找结束标题
            end_idx = TitleMatcher.find_title_in_content_list(
                end_title,
                content_list,
                page_range
            )
            if end_idx is None:
                # 找不到结束标题，使用页面范围内的最后一个content的索引
                if page_range:
                    # 找到最后一个在页面范围内的content的索引
                    for i in range(len(content_list) - 1, -1, -1):
                        if page_range[0] <= content_list[i].get("page_idx", -1) <= page_range[1]:
                            end_idx = i + 1  # +1因为range不包含结束索引
                            break
                    else:
                        end_idx = len(content_list)
                else:
                    end_idx = len(content_list)
        else:
            # 没有结束标题，使用页面范围内的最后一个content的索引
            if page_range:
                # 找到最后一个在页面范围内的content的索引
                for i in range(len(content_list) - 1, -1, -1):
                    if page_range[0] <= content_list[i].get("page_idx", -1) <= page_range[1]:
                        end_idx = i + 1  # +1因为range不包含结束索引
                        break
                else:
                    end_idx = len(content_list)
            else:
                end_idx = len(content_list)
        
        # 3. 提取范围内的content（不包含标题本身）
        # start_idx + 1: 跳过起始标题
        # end_idx: 不包含结束标题
        result = []
        for i in range(start_idx + 1, min(end_idx, len(content_list))):
            content = content_list[i]
            
            # 检查页面范围
            if page_range:
                page_idx = content.get("page_idx", -1)
                if not (page_range[0] <= page_idx <= page_range[1]):
                    continue
            
            result.append(content)
        
        return result
    
    @staticmethod
    def extract_text_from_contents(contents: List[Dict[str, Any]]) -> str:
        """
        从content列表中提取文本并拼接
        
        Args:
            contents: MinerU的content列表
            
        Returns:
            拼接后的文本
        """
        text_parts = []
        
        for content in contents:
            content_type = content.get("type", "")
            
            if content_type == "text":
                text = content.get("text", "")
                if text:
                    text_parts.append(text)
            
            elif content_type == "list":
                list_items = content.get("list_items", [])
                if list_items:
                    # list每项换行
                    text_parts.append("\n".join(list_items))
            
            elif content_type == "image":
                # 图片转换为Markdown格式
                img_path = content.get("img_path", "")
                caption = content.get("image_caption", [])
                if img_path:
                    if caption:
                        caption_text = " ".join(caption)
                        text_parts.append(f"![{caption_text}]({img_path})")
                    else:
                        # 使用文件名作为caption
                        import os
                        filename = os.path.basename(img_path)
                        text_parts.append(f"![{filename}]({img_path})")
            
            elif content_type == "table":
                # 表格转换为Markdown格式
                img_path = content.get("img_path", "")
                caption = content.get("table_caption", [])
                if img_path:
                    if caption:
                        caption_text = " ".join(caption)
                        text_parts.append(f"![{caption_text}]({img_path})")
                    else:
                        # 使用文件名作为caption
                        import os
                        filename = os.path.basename(img_path)
                        text_parts.append(f"![{filename}]({img_path})")
        
        # 用双换行符连接各部分
        return "\n\n".join(text_parts)


def extract_bbox_positions(contents: List[Dict[str, Any]]) -> List[List[int]]:
    """
    从content列表中提取所有bbox坐标
    
    Args:
        contents: MinerU的content列表
        
    Returns:
        bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]
    """
    positions = []
    
    for content in contents:
        bbox = content.get("bbox")
        page_idx = content.get("page_idx")
        
        # 只提取包含bbox和page_idx的content
        if bbox and page_idx is not None and len(bbox) == 4:
            # 格式：[page_idx, x1, y1, x2, y2]
            position = [page_idx] + bbox
            positions.append(position)
    
    return positions


def extract_bbox_positions_with_titles(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None
) -> List[List[int]]:
    """
    根据标题范围提取bbox坐标（闭区间起始标题，开区间结束标题）
    
    Args:
        start_title: 起始标题（闭区间，包含该标题）
        end_title: 结束标题（开区间，不包含该标题）
        content_list: MinerU解析的content列表
        page_range: 页面范围（start_page, end_page）
        
    Returns:
        bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]
    """
    # 1. 查找起始标题索引
    start_idx = TitleMatcher.find_title_in_content_list(
        start_title,
        content_list,
        page_range
    )
    
    if start_idx is None:
        # 找不到起始标题，尝试fallback策略
        # 对于有子节点的父节点，或者结构性标题，可能在content_list中找不到
        # 此时应该提取整个页面范围的bbox作为fallback
        if page_range is not None:
            # Fallback: 提取整个页面范围内的所有bbox
            positions = []
            for content in content_list:
                page_idx = content.get("page_idx", -1)
                # 检查是否在页面范围内
                if page_range[0] <= page_idx <= page_range[1]:
                    bbox = content.get("bbox")
                    if bbox and len(bbox) == 4:
                        position = [page_idx] + bbox
                        positions.append(position)
            return positions
        else:
            # 没有页面范围，无法fallback，返回空列表
            return []
    
    # 2. 确定结束索引（与find_content_range_by_titles逻辑相同）
    if end_title:
        # 查找结束标题
        end_idx = TitleMatcher.find_title_in_content_list(
            end_title,
            content_list,
            page_range
        )
        if end_idx is None:
            # 找不到结束标题，使用页面范围内的最后一个content的索引
            if page_range:
                for i in range(len(content_list) - 1, -1, -1):
                    if page_range[0] <= content_list[i].get("page_idx", -1) <= page_range[1]:
                        end_idx = i + 1
                        break
                else:
                    end_idx = len(content_list)
            else:
                end_idx = len(content_list)
    else:
        # 没有结束标题，使用页面范围内的最后一个content的索引
        if page_range:
            for i in range(len(content_list) - 1, -1, -1):
                if page_range[0] <= content_list[i].get("page_idx", -1) <= page_range[1]:
                    end_idx = i + 1
                    break
            else:
                end_idx = len(content_list)
        else:
            end_idx = len(content_list)
    
    # 3. 提取范围内的content的bbox（包含起始标题，不包含结束标题）
    # start_idx: 包含起始标题（闭区间）
    # end_idx: 不包含结束标题（开区间）
    #
    # 特殊情况：当start_idx == end_idx时（同一个content包含多个标题，如目录list）
    # 仍然需要提取这个content的bbox
    positions = []
    
    # 确保至少提取起始content的bbox
    actual_end_idx = max(end_idx, start_idx + 1)
    
    for i in range(start_idx, min(actual_end_idx, len(content_list))):
        content = content_list[i]
        
        # 检查页面范围
        if page_range:
            page_idx = content.get("page_idx", -1)
            if not (page_range[0] <= page_idx <= page_range[1]):
                continue
        
        # 提取bbox
        bbox = content.get("bbox")
        page_idx = content.get("page_idx")
        
        if bbox and page_idx is not None and len(bbox) == 4:
            # 格式：[page_idx, x1, y1, x2, y2]
            position = [page_idx] + bbox
            positions.append(position)
    
    return positions


# 便捷函数
def find_title_match(
    title: str,
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None
) -> Optional[int]:
    """
    便捷函数：查找标题在content_list中的索引
    
    Args:
        title: 目标标题
        content_list: MinerU解析的content列表
        page_range: 页面范围（start_page, end_page）
        
    Returns:
        找到的索引，未找到返回None
    """
    return TitleMatcher.find_title_in_content_list(title, content_list, page_range)


def extract_content_by_title_range(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None
) -> str:
    """
    便捷函数：根据标题范围提取内容并转换为文本
    
    Args:
        start_title: 起始标题（完整标题，包含序号）
        end_title: 结束标题（None表示到结尾）
        content_list: MinerU解析的content列表
        page_range: 页面范围（start_page, end_page）
        
    Returns:
        提取的文本内容
    """
    contents = TitleMatcher.find_content_range_by_titles(
        start_title,
        end_title,
        content_list,
        page_range
    )
    
    return TitleMatcher.extract_text_from_contents(contents)