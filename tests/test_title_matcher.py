"""
标题匹配算法单元测试
"""

import pytest
from app.utils.title_matcher import TitleMatcher, find_title_match, extract_content_by_title_range


class TestTitleNormalization:
    """测试标题归一化"""
    
    def test_remove_spaces(self):
        """测试去除空格"""
        title = "第二章 系统建设要求"
        normalized = TitleMatcher.normalize_title(title)
        expected = "第二章系统建设要求".lower()
        assert normalized == expected
    
    def test_remove_punctuation(self):
        """测试去除标点符号"""
        title = "§2.1. 基础功能部分"
        normalized = TitleMatcher.normalize_title(title)
        # §符号保留，但.被移除
        assert "§" in normalized
        assert "." not in normalized
    
    def test_lowercase_conversion(self):
        """测试转小写"""
        title = "System Requirements"
        normalized = TitleMatcher.normalize_title(title)
        assert normalized == normalized.lower()
    
    def test_empty_string(self):
        """测试空字符串"""
        assert TitleMatcher.normalize_title("") == ""
        assert TitleMatcher.normalize_title(None) == ""


class TestTitleContainment:
    """测试标题包含判断"""
    
    def test_exact_match(self):
        """测试精确匹配"""
        target = "第二章 系统建设要求"
        content = "第二章 系统建设要求"
        assert TitleMatcher.is_title_contained(target, content)
    
    def test_space_difference(self):
        """测试空格差异"""
        target = "第二章 系统建设要求"
        content = "第二章系统建设要求"
        assert TitleMatcher.is_title_contained(target, content)
    
    def test_contained_in_longer_text(self):
        """测试包含在更长文本中"""
        target = "§2.1. 基础功能部分"
        content = "§2.1. 基础功能部分§2.1.1. 企业用户"
        assert TitleMatcher.is_title_contained(target, content)
    
    def test_no_match(self):
        """测试不匹配"""
        target = "第一章 概述"
        content = "第二章 系统建设要求"
        assert not TitleMatcher.is_title_contained(target, content)
    
    def test_partial_match_with_high_similarity(self):
        """测试高相似度部分匹配"""
        target = "系统性能要求"
        content = "系统性能和安全要求"
        # 这个应该返回True，因为相似度高
        result = TitleMatcher.is_title_contained(target, content, similarity_threshold=0.7)
        assert result


class TestFindTitleInContentList:
    """测试在content_list中查找标题"""
    
    def test_find_text_type(self):
        """测试查找text类型的标题"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
            {"type": "text", "text": "第二章 系统建设要求", "page_idx": 2},
        ]
        
        idx = TitleMatcher.find_title_in_content_list("第一章 概述", content_list)
        assert idx == 0
        
        idx = TitleMatcher.find_title_in_content_list("第二章 系统建设要求", content_list)
        assert idx == 1
    
    def test_find_in_list_type(self):
        """测试查找list类型中的标题"""
        content_list = [
            {
                "type": "list",
                "list_items": [
                    "§1.1. 建设背景. 3",
                    "§1.2. 建设目标. 3"
                ],
                "page_idx": 1
            }
        ]
        
        idx = TitleMatcher.find_title_in_content_list("§1.1. 建设背景", content_list)
        assert idx == 0
    
    def test_page_range_filter(self):
        """测试页面范围过滤"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
            {"type": "text", "text": "第二章 系统建设要求", "page_idx": 5},
        ]
        
        # 查找页面1-3范围内的
        idx = TitleMatcher.find_title_in_content_list(
            "第二章 系统建设要求",
            content_list,
            page_range=(1, 3)
        )
        assert idx is None  # 应该找不到，因为不在页面范围内
        
        # 扩大范围
        idx = TitleMatcher.find_title_in_content_list(
            "第二章 系统建设要求",
            content_list,
            page_range=(1, 10)
        )
        assert idx == 1
    
    def test_not_found(self):
        """测试找不到的情况"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
        ]
        
        idx = TitleMatcher.find_title_in_content_list("第三章", content_list)
        assert idx is None


class TestFindContentRangeByTitles:
    """测试根据标题范围查找内容"""
    
    def test_range_with_end_title(self):
        """测试有结束标题的情况"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
            {"type": "text", "text": "这是第一章的内容", "page_idx": 1},
            {"type": "text", "text": "还有更多内容", "page_idx": 1},
            {"type": "text", "text": "第二章 系统建设要求", "page_idx": 2},
        ]
        
        result = TitleMatcher.find_content_range_by_titles(
            start_title="第一章 概述",
            end_title="第二章 系统建设要求",
            content_list=content_list
        )
        
        # 应该返回中间的两项（不包含标题本身）
        assert len(result) == 2
        assert result[0]["text"] == "这是第一章的内容"
        assert result[1]["text"] == "还有更多内容"
    
    def test_range_without_end_title(self):
        """测试没有结束标题的情况（到结尾）"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
            {"type": "text", "text": "这是第一章的内容", "page_idx": 1},
            {"type": "text", "text": "还有更多内容", "page_idx": 1},
        ]
        
        result = TitleMatcher.find_content_range_by_titles(
            start_title="第一章 概述",
            end_title=None,
            content_list=content_list,
            page_range=(1, 1)
        )
        
        # 应该返回标题后的所有内容
        assert len(result) == 2


class TestExtractTextFromContents:
    """测试从content列表提取文本"""
    
    def test_extract_text_type(self):
        """测试提取text类型"""
        contents = [
            {"type": "text", "text": "这是第一段"},
            {"type": "text", "text": "这是第二段"},
        ]
        
        text = TitleMatcher.extract_text_from_contents(contents)
        assert "这是第一段" in text
        assert "这是第二段" in text
    
    def test_extract_list_type(self):
        """测试提取list类型"""
        contents = [
            {
                "type": "list",
                "list_items": ["项目1", "项目2", "项目3"]
            }
        ]
        
        text = TitleMatcher.extract_text_from_contents(contents)
        assert "项目1" in text
        assert "项目2" in text
        assert "项目3" in text
    
    def test_extract_image_type(self):
        """测试提取image类型（转为Markdown）"""
        contents = [
            {
                "type": "image",
                "img_path": "images/test.jpg",
                "image_caption": ["图1", "测试图片"]
            }
        ]
        
        text = TitleMatcher.extract_text_from_contents(contents)
        assert "![图1 测试图片](images/test.jpg)" in text
    
    def test_extract_image_without_caption(self):
        """测试提取无caption的image"""
        contents = [
            {
                "type": "image",
                "img_path": "images/test.jpg",
                "image_caption": []
            }
        ]
        
        text = TitleMatcher.extract_text_from_contents(contents)
        # 应该使用文件名作为caption
        assert "![test.jpg](images/test.jpg)" in text
    
    def test_extract_table_type(self):
        """测试提取table类型（转为Markdown）"""
        contents = [
            {
                "type": "table",
                "img_path": "images/table.jpg",
                "table_caption": ["表1", "测试表格"],
                "table_body": "<table>...</table>"
            }
        ]
        
        text = TitleMatcher.extract_text_from_contents(contents)
        assert "![表1 测试表格](images/table.jpg)" in text
    
    def test_extract_mixed_types(self):
        """测试混合类型提取"""
        contents = [
            {"type": "text", "text": "前言"},
            {"type": "list", "list_items": ["要点1", "要点2"]},
            {"type": "image", "img_path": "images/fig1.jpg", "image_caption": ["图1"]},
            {"type": "text", "text": "结论"},
        ]
        
        text = TitleMatcher.extract_text_from_contents(contents)
        assert "前言" in text
        assert "要点1" in text
        assert "![图1](images/fig1.jpg)" in text
        assert "结论" in text


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    def test_find_title_match(self):
        """测试find_title_match便捷函数"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
        ]
        
        idx = find_title_match("第一章 概述", content_list)
        assert idx == 0
    
    def test_extract_content_by_title_range(self):
        """测试extract_content_by_title_range便捷函数"""
        content_list = [
            {"type": "text", "text": "第一章 概述", "page_idx": 1},
            {"type": "text", "text": "这是内容", "page_idx": 1},
            {"type": "text", "text": "第二章", "page_idx": 2},
        ]
        
        text = extract_content_by_title_range(
            "第一章 概述",
            "第二章",
            content_list
        )
        
        assert "这是内容" in text
        assert "第一章 概述" not in text  # 标题本身不应该在内容中
        assert "第二章" not in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])