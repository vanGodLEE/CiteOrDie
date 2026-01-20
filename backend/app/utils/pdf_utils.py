"""
PDF工具函数

提供PDF文件的基本信息读取功能
"""

from typing import Dict, List, Tuple
from pathlib import Path
from loguru import logger


def get_pdf_page_dimensions(pdf_path: str) -> List[Tuple[float, float]]:
    """
    获取PDF所有页面的尺寸
    
    Args:
        pdf_path: PDF文件路径
    
    Returns:
        页面尺寸列表 [(width, height), ...]，单位：points
    
    Raises:
        FileNotFoundError: PDF文件不存在
        Exception: PDF读取失败
    """
    try:
        import PyPDF2
        
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            dimensions = []
            
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                # 获取MediaBox（页面尺寸）
                media_box = page.mediabox
                width = float(media_box.width)
                height = float(media_box.height)
                dimensions.append((width, height))
            
            logger.debug(
                f"读取PDF尺寸成功: {pdf_path_obj.name}, "
                f"{len(dimensions)} 页, "
                f"首页尺寸={dimensions[0] if dimensions else 'N/A'}"
            )
            
            return dimensions
            
    except ImportError:
        logger.warning("PyPDF2未安装，使用默认A4尺寸")
        # 返回A4尺寸作为默认值
        return [(595.0, 842.0)] * 100  # 假设最多100页
        
    except Exception as e:
        logger.error(f"读取PDF尺寸失败: {e}")
        # 返回A4尺寸作为默认值
        return [(595.0, 842.0)] * 100


def get_pdf_page_height(pdf_path: str, page_index: int = 0) -> float:
    """
    获取PDF指定页面的高度
    
    Args:
        pdf_path: PDF文件路径
        page_index: 页面索引（0-based）
    
    Returns:
        页面高度（points）
    """
    try:
        dimensions = get_pdf_page_dimensions(pdf_path)
        if page_index < len(dimensions):
            return dimensions[page_index][1]
        else:
            logger.warning(
                f"页面索引 {page_index} 超出范围，使用首页高度"
            )
            return dimensions[0][1] if dimensions else 842.0
    except Exception as e:
        logger.warning(f"获取页面高度失败，使用A4默认值: {e}")
        return 842.0  # A4高度


def get_average_page_height(pdf_path: str) -> float:
    """
    获取PDF所有页面的平均高度
    
    适用于页面尺寸统一的文档（如招标文件）
    
    Args:
        pdf_path: PDF文件路径
    
    Returns:
        平均页面高度（points）
    """
    try:
        dimensions = get_pdf_page_dimensions(pdf_path)
        if not dimensions:
            return 842.0  # A4默认值
        
        heights = [h for w, h in dimensions]
        avg_height = sum(heights) / len(heights)
        
        logger.debug(
            f"PDF平均页面高度: {avg_height:.2f} points "
            f"({len(heights)} 页)"
        )
        
        return avg_height
        
    except Exception as e:
        logger.warning(f"计算平均页面高度失败，使用A4默认值: {e}")
        return 842.0


def detect_page_size_name(width: float, height: float) -> str:
    """
    根据尺寸检测页面类型
    
    Args:
        width: 页面宽度（points）
        height: 页面高度（points）
    
    Returns:
        页面类型名称（A4/A3/Letter/Legal/Custom）
    """
    # 标准页面尺寸（允许±5 points误差）
    tolerance = 5.0
    
    standard_sizes = {
        "A4": (595.0, 842.0),
        "A3": (842.0, 1191.0),
        "Letter": (612.0, 792.0),
        "Legal": (612.0, 1008.0),
    }
    
    for name, (std_width, std_height) in standard_sizes.items():
        if (abs(width - std_width) < tolerance and 
            abs(height - std_height) < tolerance):
            return name
    
    return "Custom"