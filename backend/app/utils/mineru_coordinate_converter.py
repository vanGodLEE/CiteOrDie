"""
MinerU坐标转换工具（参考RAGFlow实现）

MinerU坐标系统：
- 格式：[x0, y0, x1, y1]
- 范围：0-1000（归一化坐标）
- 原点：左上角
- Y轴方向：向下

转换步骤（参考RAGFlow）：
1. 将MinerU的0-1000归一化坐标转换为页面实际坐标（乘以页面宽高）
2. ✅ 无需Y轴翻转！保持左上原点，Y轴向下
3. 前端Canvas可直接使用（Canvas也是左上原点）

重要：使用pdfplumber获取页面尺寸（与RAGFlow一致，避免坐标偏移）
"""

from typing import List, Tuple
import pdfplumber
from loguru import logger


def convert_mineru_to_page_rect(
    bbox: List[int],
    page_width: float,
    page_height: float
) -> List[float]:
    """
    将MinerU的归一化坐标(0-1000)转换为实际页面坐标
    参考RAGFlow实现，直接转换，不做Y轴翻转
    
    Args:
        bbox: MinerU bbox [x0, y0, x1, y1], 0-1000范围
        page_width: PDF页面宽度(points)
        page_height: PDF页面高度(points)
    
    Returns:
        Page rect [x0, y0, x1, y1], 左上角原点，单位points
    
    示例：
        MinerU bbox: [213, 253, 784, 317] (归一化0-1000)
        页面尺寸: 612x792 points (Letter size)
        
        转换为页面坐标（左上原点）：
        x0 = 213/1000 * 612 = 130.356
        y0 = 253/1000 * 792 = 200.376
        x1 = 784/1000 * 612 = 479.808
        y1 = 317/1000 * 792 = 251.064
        
        返回: [130.356, 200.376, 479.808, 251.064]
    """
    x0_norm, y0_norm, x1_norm, y1_norm = bbox
    
    # 直接转换归一化坐标为实际坐标（保持左上原点，Y轴向下）
    x0 = (x0_norm / 1000.0) * page_width
    x1 = (x1_norm / 1000.0) * page_width
    y0 = (y0_norm / 1000.0) * page_height
    y1 = (y1_norm / 1000.0) * page_height
    
    return [x0, y0, x1, y1]


def convert_positions_for_frontend(
    positions: List[List[int]],
    pdf_path: str = None,
    page_dimensions: List[Tuple[float, float]] = None
) -> List[List[float]]:
    """
    批量转换positions数组为页面坐标系统（左上原点）
    
    参考RAGFlow实现：
    1. ✅ 使用pdfplumber获取页面尺寸（与RAGFlow一致，避免坐标偏移）
    2. 直接转换归一化坐标，不做Y轴翻转
    
    Args:
        positions: [[page_idx, x0, y0, x1, y1], ...] (MinerU格式，0-based页码，归一化0-1000)
        pdf_path: PDF文件路径（如果未提供page_dimensions则必需）
        page_dimensions: 预先获取的页面尺寸列表 [(width, height), ...] (性能优化，避免重复打开PDF)
    
    Returns:
        [[page_idx, x0, y0, x1, y1], ...] (页面坐标，0-based页码，左上原点，单位points)
    """
    if not positions:
        return []
    
    # 如果已经提供了page_dimensions，直接使用（性能优化）
    if page_dimensions is None:
        if pdf_path is None:
            raise ValueError("必须提供 pdf_path 或 page_dimensions")
        
        # ✅ 关键修复：使用pdfplumber获取页面尺寸（与RAGFlow完全一致）
        with pdfplumber.open(pdf_path) as pdf:
            # 预先获取所有页面尺寸
            page_dimensions = [(page.width, page.height) for page in pdf.pages]
            logger.info(f"[坐标转换] 使用pdfplumber获取了 {len(page_dimensions)} 页的尺寸")
            
            # 调试：打印前几页的尺寸
            for i, (w, h) in enumerate(page_dimensions[:3]):
                logger.debug(f"[坐标转换] 页面 {i}: {w:.1f} x {h:.1f} points")
    else:
        logger.debug(f"[坐标转换] 使用缓存的页面尺寸 ({len(page_dimensions)} 页)")
    
    converted_positions = []
    for pos in positions:
        page_idx, x0, y0, x1, y1 = pos
        
        # 获取该页的尺寸
        if page_idx < len(page_dimensions):
            page_width, page_height = page_dimensions[page_idx]
        else:
            logger.warning(f"[坐标转换] 页码 {page_idx} 超出范围，使用A4默认尺寸")
            page_width, page_height = 595, 842
        
        # 转换坐标（保持左上原点）
        page_rect = convert_mineru_to_page_rect(
            [x0, y0, x1, y1],
            page_width,
            page_height
        )
        
        # 保持页码，替换坐标
        converted_positions.append([page_idx] + page_rect)
    
    return converted_positions


def get_page_dimensions(pdf_path: str, page_idx: int) -> Tuple[float, float]:
    """
    获取PDF页面的宽高（使用pdfplumber，与RAGFlow一致）
    
    Args:
        pdf_path: PDF文件路径
        page_idx: 页面索引(0-based)
    
    Returns:
        (width, height) in points
    """
    with pdfplumber.open(pdf_path) as pdf:
        if page_idx < len(pdf.pages):
            page = pdf.pages[page_idx]
            return page.width, page.height
        else:
            logger.warning(f"[坐标转换] 页码 {page_idx} 超出范围，返回A4默认尺寸")
            return 595, 842


def get_all_page_dimensions(pdf_path: str) -> List[Tuple[float, float]]:
    """
    获取PDF所有页面的尺寸（用于批量转换时缓存，避免重复打开PDF）
    
    Args:
        pdf_path: PDF文件路径
    
    Returns:
        [(width, height), ...] 所有页面的尺寸列表
    """
    with pdfplumber.open(pdf_path) as pdf:
        page_dimensions = [(page.width, page.height) for page in pdf.pages]
        logger.info(f"[坐标转换] 缓存了 {len(page_dimensions)} 页的尺寸")
        return page_dimensions


# 前端使用示例（JavaScript）
"""
方案1：直接在Canvas上绘制（推荐，坐标已经是左上原点）
```javascript
// 后端返回的坐标已经是页面坐标（左上原点，单位points）
const positions = [[0, 130.356, 200.376, 479.808, 251.064]];

// 渲染PDF到Canvas
const page = await pdfDoc.getPage(pageNumber);
const viewport = page.getViewport({ scale: scale });
const canvas = document.getElementById('pdf-canvas');
canvas.width = viewport.width;
canvas.height = viewport.height;
await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;

// 创建高亮Canvas（叠加层）
const highlightCanvas = document.getElementById('highlight-canvas');
highlightCanvas.width = viewport.width;
highlightCanvas.height = viewport.height;
const ctx = highlightCanvas.getContext('2d');

// 绘制高亮框
for (const [pageIdx, x0, y0, x1, y1] of positions) {
  if (pageIdx + 1 !== pageNumber) continue;
  
  // 应用scale（坐标已经是左上原点，只需缩放）
  const vx0 = x0 * scale;
  const vy0 = y0 * scale;
  const vx1 = x1 * scale;
  const vy1 = y1 * scale;
  
  ctx.strokeStyle = 'red';
  ctx.lineWidth = 2;
  ctx.strokeRect(vx0, vy0, vx1 - vx0, vy1 - vy0);
}
```

推荐使用方案1，更简单直接。

关键修复：使用pdfplumber获取页面尺寸
- PyMuPDF (fitz) 和 pdfplumber 获取的页面尺寸可能略有差异
- RAGFlow使用pdfplumber，我们也必须使用pdfplumber以确保坐标一致
- 这是解决"稍微偏移"问题的关键
"""