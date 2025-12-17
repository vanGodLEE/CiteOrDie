"""
PDF文本提取服务

用于从PDF文件中按页码提取文本内容，支持text_filler节点精确填充原文
"""

from typing import List, Tuple, Optional
from loguru import logger
import fitz  # PyMuPDF


class PDFTextExtractor:
    """PDF文本提取器"""
    
    def __init__(self, pdf_path: str):
        """
        初始化PDF文本提取器
        
        Args:
            pdf_path: PDF文件路径
        """
        self.pdf_path = pdf_path
        self._doc = None
    
    def __enter__(self):
        """上下文管理器：打开PDF"""
        self._doc = fitz.open(self.pdf_path)
        logger.debug(f"打开PDF文件: {self.pdf_path}, 总页数: {len(self._doc)}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：关闭PDF"""
        if self._doc:
            self._doc.close()
            self._doc = None
    
    def extract_page_text(self, page_num: int) -> str:
        """
        提取单页文本
        
        Args:
            page_num: 页码（1-based）
            
        Returns:
            页面文本内容
        """
        if not self._doc:
            raise RuntimeError("PDF文档未打开，请使用with语句")
        
        if page_num < 1 or page_num > len(self._doc):
            logger.warning(f"页码 {page_num} 超出范围 [1, {len(self._doc)}]")
            return ""
        
        try:
            page = self._doc[page_num - 1]  # 0-based索引
            text = page.get_text()
            logger.debug(f"提取第 {page_num} 页文本，长度: {len(text)}")
            return text
        except Exception as e:
            logger.error(f"提取第 {page_num} 页文本失败: {e}")
            return ""
    
    def extract_pages_text(
        self, 
        start_page: int, 
        end_page: int, 
        add_page_markers: bool = True
    ) -> str:
        """
        提取多页文本
        
        Args:
            start_page: 起始页码（1-based，包含）
            end_page: 结束页码（1-based，包含）
            add_page_markers: 是否添加页码标记
            
        Returns:
            拼接后的文本内容
        """
        if not self._doc:
            raise RuntimeError("PDF文档未打开，请使用with语句")
        
        # 验证页码范围
        start_page = max(1, start_page)
        end_page = min(end_page, len(self._doc))
        
        if start_page > end_page:
            logger.warning(f"起始页 {start_page} 大于结束页 {end_page}")
            return ""
        
        text_parts = []
        
        for page_num in range(start_page, end_page + 1):
            try:
                page = self._doc[page_num - 1]
                page_text = page.get_text()
                
                if add_page_markers:
                    # 添加页码标记，便于LLM识别页面边界
                    text_parts.append(
                        f"========== 第{page_num}页 ==========\n"
                        f"{page_text}\n"
                        f"========== 第{page_num}页结束 =========="
                    )
                else:
                    text_parts.append(page_text)
                
            except Exception as e:
                logger.error(f"提取第 {page_num} 页文本失败: {e}")
                continue
        
        combined_text = "\n\n".join(text_parts)
        logger.debug(
            f"提取第 {start_page}-{end_page} 页文本完成，"
            f"总长度: {len(combined_text)}"
        )
        
        return combined_text
    
    def get_page_count(self) -> int:
        """获取PDF总页数"""
        if not self._doc:
            raise RuntimeError("PDF文档未打开，请使用with语句")
        return len(self._doc)


def extract_page_text(pdf_path: str, page_num: int) -> str:
    """
    便捷函数：提取单页文本
    
    Args:
        pdf_path: PDF文件路径
        page_num: 页码（1-based）
        
    Returns:
        页面文本内容
    """
    with PDFTextExtractor(pdf_path) as extractor:
        return extractor.extract_page_text(page_num)


def extract_pages_text(
    pdf_path: str, 
    start_page: int, 
    end_page: int,
    add_page_markers: bool = True
) -> str:
    """
    便捷函数：提取多页文本
    
    Args:
        pdf_path: PDF文件路径
        start_page: 起始页码（1-based，包含）
        end_page: 结束页码（1-based，包含）
        add_page_markers: 是否添加页码标记
        
    Returns:
        拼接后的文本内容
    """
    with PDFTextExtractor(pdf_path) as extractor:
        return extractor.extract_pages_text(start_page, end_page, add_page_markers)


def get_pdf_page_count(pdf_path: str) -> int:
    """
    便捷函数：获取PDF总页数
    
    Args:
        pdf_path: PDF文件路径
        
    Returns:
        总页数
    """
    with PDFTextExtractor(pdf_path) as extractor:
        return extractor.get_page_count()
