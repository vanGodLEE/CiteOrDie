"""
MinerU文档解析服务

提供PDF文档的完整解析功能，包括文本、图片、表格的提取
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger


class MinerUService:
    """MinerU文档解析服务"""
    
    def __init__(self, output_base_dir: str = "mineru_output"):
        """
        初始化MinerU服务
        
        Args:
            output_base_dir: MinerU输出的基础目录
        """
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(exist_ok=True)
    
    def parse_pdf(
        self,
        pdf_path: str,
        task_id: str,
        backend: str = "pipeline",
        device: str = "cuda"
    ) -> Optional[Dict[str, Any]]:
        """
        使用MinerU解析PDF文档
        
        Args:
            pdf_path: PDF文件路径
            task_id: 任务ID（用于隔离输出目录）
            backend: MinerU后端引擎（默认: pipeline，输出到auto文件夹）
            device: 运行设备（cuda/cpu，默认: cuda）
            
        Returns:
            解析结果字典，包含:
            - content_list: 内容列表
            - output_dir: 输出目录路径
            - images_dir: 图片目录路径
            - md_path: Markdown文件路径
        """
        try:
            # 1. 验证PDF文件存在
            if not os.path.exists(pdf_path):
                logger.error(f"PDF文件不存在: {pdf_path}")
                return None
            
            # 2. 创建任务专属输出目录
            task_output_dir = self.output_base_dir / task_id
            task_output_dir.mkdir(exist_ok=True)
            
            # 3. 构建MinerU命令
            cmd = [
                "mineru",
                "-p", pdf_path,
                "-o", str(task_output_dir),
                "-b", backend,
                "-d", device
            ]
            
            logger.info(f"开始调用MinerU解析PDF: {pdf_path}")
            logger.info(f"命令: {' '.join(cmd)}")
            
            # 4. 执行MinerU命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            if result.returncode != 0:
                logger.error(f"MinerU解析失败，返回码: {result.returncode}")
                logger.error(f"错误输出: {result.stderr}")
                return None
            
            logger.info("MinerU解析完成")
            logger.debug(f"输出: {result.stdout}")
            
            # 5. 解析输出目录结构
            # MinerU的输出结构: output_dir/{pdf_name}/{backend}/{pdf_name}_content_list.json
            pdf_name = Path(pdf_path).stem
            pdf_output_dir = task_output_dir / pdf_name
            
            # MinerU会转换backend名称（如 pipeline -> auto）
            # 因此我们需要扫描实际存在的目录
            if not pdf_output_dir.exists():
                logger.error(f"PDF输出目录不存在: {pdf_output_dir}")
                return None
            
            # 查找实际的backend目录
            backend_dirs = [d for d in pdf_output_dir.iterdir() if d.is_dir()]
            if not backend_dirs:
                logger.error(f"未找到backend输出目录: {pdf_output_dir}")
                return None
            
            # 使用第一个目录（通常只有一个）
            content_dir = backend_dirs[0]
            logger.info(f"找到MinerU输出目录: {content_dir}")
            
            # 6. 加载content_list.json
            content_list_path = content_dir / f"{pdf_name}_content_list.json"
            if not content_list_path.exists():
                logger.error(f"content_list.json不存在: {content_list_path}")
                return None
            
            with open(content_list_path, 'r', encoding='utf-8') as f:
                content_list = json.load(f)
            
            logger.info(f"成功加载content_list，包含 {len(content_list)} 个内容项")
            
            # 7. 构建返回结果
            result_data = {
                "content_list": content_list,
                "output_dir": str(content_dir),
                "images_dir": str(content_dir / "images"),
                "md_path": str(content_dir / f"{pdf_name}.md"),
                "pdf_name": pdf_name,
                "total_items": len(content_list)
            }
            
            # 8. 统计内容类型
            type_counts = self._count_content_types(content_list)
            result_data["type_counts"] = type_counts
            
            logger.info(f"内容统计: {type_counts}")
            
            return result_data
            
        except Exception as e:
            logger.error(f"MinerU解析异常: {str(e)}")
            logger.exception(e)
            return None
    
    def _count_content_types(self, content_list: List[Dict]) -> Dict[str, int]:
        """
        统计content_list中各类型内容的数量
        
        Args:
            content_list: MinerU解析的内容列表
            
        Returns:
            类型统计字典
        """
        type_counts = {
            "text": 0,
            "list": 0,
            "image": 0,
            "table": 0,
            "other": 0
        }
        
        for item in content_list:
            item_type = item.get("type", "other")
            if item_type in type_counts:
                type_counts[item_type] += 1
            else:
                type_counts["other"] += 1
        
        return type_counts
    
    def get_content_by_page(
        self,
        content_list: List[Dict],
        page_idx: int
    ) -> List[Dict]:
        """
        获取指定页面的所有内容
        
        Args:
            content_list: MinerU解析的内容列表
            page_idx: 页面索引（0-based）
            
        Returns:
            该页面的内容列表
        """
        return [
            item for item in content_list
            if item.get("page_idx") == page_idx
        ]
    
    def get_content_range(
        self,
        content_list: List[Dict],
        start_page: int,
        end_page: int
    ) -> List[Dict]:
        """
        获取页面范围内的所有内容
        
        Args:
            content_list: MinerU解析的内容列表
            start_page: 起始页面（0-based）
            end_page: 结束页面（0-based，包含）
            
        Returns:
            页面范围内的内容列表
        """
        return [
            item for item in content_list
            if start_page <= item.get("page_idx", -1) <= end_page
        ]


# 全局MinerU服务实例
_mineru_service: Optional[MinerUService] = None


def get_mineru_service() -> MinerUService:
    """
    获取全局MinerU服务实例（单例模式）
    
    Returns:
        MinerU服务实例
    """
    global _mineru_service
    if _mineru_service is None:
        _mineru_service = MinerUService()
    return _mineru_service