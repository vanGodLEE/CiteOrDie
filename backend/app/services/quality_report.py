"""
质量报告服务

用于分析结束后生成质量报告，包含以下指标：
1. 精度解析平均置信度：从MinerU的middle.json中计算所有score字段的平均值
2. 原文抽取的成功率：检查标题间是否有原文且成功抽取
3. 原文匹配bbox的成功率：原文是否成功匹配到bbox坐标
4. 条款对应原文bbox匹配的成功率：条款是否有positions
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from loguru import logger


class QualityReport(BaseModel):
    """质量报告数据模型"""
    
    # 1. 精度解析平均置信度
    avg_parse_confidence: float = Field(
        ..., 
        description="MinerU解析平均置信度（0-1），从middle.json的score字段计算"
    )
    total_score_count: int = Field(
        ..., 
        description="参与计算的score字段总数"
    )
    
    # 2. 原文抽取的成功率
    content_extraction_success_rate: float = Field(
        ..., 
        description="原文抽取成功率（0-1），标题间有原文且成功抽取的比例"
    )
    total_sections: int = Field(
        ..., 
        description="参与评估的章节总数"
    )
    sections_with_content: int = Field(
        ..., 
        description="成功抽取原文的章节数"
    )
    
    # 3. 原文匹配bbox的成功率
    content_bbox_match_rate: float = Field(
        ..., 
        description="原文匹配bbox成功率（0-1），原文是否有positions坐标"
    )
    sections_with_bbox: int = Field(
        ..., 
        description="有bbox坐标的章节数"
    )
    
    # 4. 条款对应原文bbox匹配的成功率
    clause_bbox_match_rate: float = Field(
        ..., 
        description="条款bbox匹配成功率（0-1），条款是否有positions坐标"
    )
    total_clauses: int = Field(
        ..., 
        description="条款总数"
    )
    clauses_with_bbox: int = Field(
        ..., 
        description="有bbox坐标的条款数"
    )
    
    # 元数据
    generated_at: str = Field(
        ..., 
        description="报告生成时间"
    )
    pdf_name: str = Field(
        default="", 
        description="PDF文件名"
    )


class QualityReportService:
    """质量报告服务"""
    
    @staticmethod
    def calculate_parse_confidence(middle_json_path: str) -> Dict[str, Any]:
        """
        计算解析平均置信度（指标1）
        
        从MinerU的middle.json中提取所有score字段并计算平均值
        
        Args:
            middle_json_path: middle.json文件路径
            
        Returns:
            包含avg_confidence和total_count的字典
        """
        try:
            with open(middle_json_path, 'r', encoding='utf-8') as f:
                middle_data = json.load(f)
            
            scores = []
            
            # 遍历所有页面
            for page in middle_data.get("pdf_info", []):
                # 遍历所有段落块
                for para_block in page.get("para_blocks", []):
                    # 遍历所有行
                    for line in para_block.get("lines", []):
                        # 遍历所有span
                        for span in line.get("spans", []):
                            score = span.get("score")
                            if score is not None:
                                scores.append(float(score))
            
            if scores:
                avg_confidence = sum(scores) / len(scores)
                logger.info(f"✓ 解析置信度统计: 平均={avg_confidence:.4f}, 样本数={len(scores)}")
                return {
                    "avg_confidence": avg_confidence,
                    "total_count": len(scores)
                }
            else:
                logger.warning("未找到任何score字段")
                return {
                    "avg_confidence": 0.0,
                    "total_count": 0
                }
                
        except Exception as e:
            logger.error(f"计算解析置信度失败: {e}")
            return {
                "avg_confidence": 0.0,
                "total_count": 0
            }
    
    @staticmethod
    def calculate_content_extraction_rate(document_tree: dict) -> Dict[str, Any]:
        """
        计算原文抽取成功率（指标2）
        
        递归遍历文档树，检查每个节点是否有clauses（原文内容）
        
        Args:
            document_tree: PageIndex文档树（字典格式）
            
        Returns:
            包含success_rate, total_sections, sections_with_content的字典
        """
        total_sections = 0
        sections_with_content = 0
        
        def traverse_node(node: dict):
            nonlocal total_sections, sections_with_content
            
            # 统计叶子节点（实际的内容章节）
            if not node.get("nodes") or len(node.get("nodes", [])) == 0:
                total_sections += 1
                
                # 检查是否有clauses（原文内容）
                clauses = node.get("clauses", [])
                if clauses and len(clauses) > 0:
                    sections_with_content += 1
            
            # 递归处理子节点
            for child in node.get("nodes", []):
                traverse_node(child)
        
        # 遍历根节点
        for root_node in document_tree.get("structure", []):
            traverse_node(root_node)
        
        success_rate = sections_with_content / total_sections if total_sections > 0 else 0.0
        
        logger.info(f"✓ 原文抽取统计: 成功率={success_rate:.2%}, 成功={sections_with_content}/{total_sections}")
        
        return {
            "success_rate": success_rate,
            "total_sections": total_sections,
            "sections_with_content": sections_with_content
        }
    
    @staticmethod
    def calculate_content_bbox_rate(document_tree: dict) -> Dict[str, Any]:
        """
        计算原文匹配bbox成功率（指标3）
        
        检查每个节点是否有positions坐标
        
        Args:
            document_tree: PageIndex文档树（字典格式）
            
        Returns:
            包含bbox_rate, total_sections, sections_with_bbox的字典
        """
        total_sections = 0
        sections_with_bbox = 0
        
        def traverse_node(node: dict):
            nonlocal total_sections, sections_with_bbox
            
            # 统计叶子节点
            if not node.get("nodes") or len(node.get("nodes", [])) == 0:
                total_sections += 1
                
                # 检查是否有positions
                positions = node.get("positions", [])
                if positions and len(positions) > 0:
                    sections_with_bbox += 1
            
            # 递归处理子节点
            for child in node.get("nodes", []):
                traverse_node(child)
        
        # 遍历根节点
        for root_node in document_tree.get("structure", []):
            traverse_node(root_node)
        
        bbox_rate = sections_with_bbox / total_sections if total_sections > 0 else 0.0
        
        logger.info(f"✓ 原文bbox统计: 成功率={bbox_rate:.2%}, 成功={sections_with_bbox}/{total_sections}")
        
        return {
            "bbox_rate": bbox_rate,
            "total_sections": total_sections,
            "sections_with_bbox": sections_with_bbox
        }
    
    @staticmethod
    def calculate_clause_bbox_rate(clauses: List[dict]) -> Dict[str, Any]:
        """
        计算条款bbox匹配成功率（指标4）
        
        检查每个条款是否有positions坐标
        
        Args:
            clauses: 条款列表（字典格式）
            
        Returns:
            包含bbox_rate, total_clauses, clauses_with_bbox的字典
        """
        total_clauses = len(clauses)
        clauses_with_bbox = 0
        
        for clause in clauses:
            positions = clause.get("positions", [])
            if positions and len(positions) > 0:
                clauses_with_bbox += 1
        
        bbox_rate = clauses_with_bbox / total_clauses if total_clauses > 0 else 0.0
        
        logger.info(f"✓ 条款bbox统计: 成功率={bbox_rate:.2%}, 成功={clauses_with_bbox}/{total_clauses}")
        
        return {
            "bbox_rate": bbox_rate,
            "total_clauses": total_clauses,
            "clauses_with_bbox": clauses_with_bbox
        }
    
    @staticmethod
    def generate_report(
        pdf_path: str,
        document_tree: dict,
        final_matrix: List[dict]
    ) -> QualityReport:
        """
        生成完整的质量报告
        
        Args:
            pdf_path: PDF文件路径
            document_tree: PageIndex文档树
            final_matrix: 最终条款矩阵
            
        Returns:
            QualityReport对象
        """
        from datetime import datetime
        
        logger.info("=== 开始生成质量报告 ===")
        
        # 查找middle.json文件
        pdf_path_obj = Path(pdf_path)
        pdf_name = pdf_path_obj.stem
        
        # MinerU输出目录：mineru_output/{task_id}/{pdf_name}/auto/
        middle_json_path = None
        mineru_output_dir = Path("mineru_output")
        
        # 遍历查找最新的middle.json
        if mineru_output_dir.exists():
            for task_dir in sorted(mineru_output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                potential_path = task_dir / pdf_name / "auto" / f"{pdf_name}_middle.json"
                if potential_path.exists():
                    middle_json_path = str(potential_path)
                    break
        
        # 1. 计算解析置信度
        parse_stats = {"avg_confidence": 0.0, "total_count": 0}
        if middle_json_path:
            logger.info(f"找到middle.json: {middle_json_path}")
            parse_stats = QualityReportService.calculate_parse_confidence(middle_json_path)
        else:
            logger.warning(f"未找到middle.json文件，跳过解析置信度计算")
        
        # 2. 计算原文抽取成功率
        content_stats = QualityReportService.calculate_content_extraction_rate(document_tree)
        
        # 3. 计算原文bbox成功率
        bbox_stats = QualityReportService.calculate_content_bbox_rate(document_tree)
        
        # 4. 计算条款bbox成功率
        clause_stats = QualityReportService.calculate_clause_bbox_rate(final_matrix)
        
        # 生成报告
        report = QualityReport(
            avg_parse_confidence=parse_stats["avg_confidence"],
            total_score_count=parse_stats["total_count"],
            content_extraction_success_rate=content_stats["success_rate"],
            total_sections=content_stats["total_sections"],
            sections_with_content=content_stats["sections_with_content"],
            content_bbox_match_rate=bbox_stats["bbox_rate"],
            sections_with_bbox=bbox_stats["sections_with_bbox"],
            clause_bbox_match_rate=clause_stats["bbox_rate"],
            total_clauses=clause_stats["total_clauses"],
            clauses_with_bbox=clause_stats["clauses_with_bbox"],
            generated_at=datetime.now().isoformat(),
            pdf_name=pdf_name
        )
        
        logger.success("=== 质量报告生成完成 ===")
        logger.info(f"  - 解析置信度: {report.avg_parse_confidence:.2%}")
        logger.info(f"  - 原文抽取成功率: {report.content_extraction_success_rate:.2%}")
        logger.info(f"  - 原文bbox匹配率: {report.content_bbox_match_rate:.2%}")
        logger.info(f"  - 条款bbox匹配率: {report.clause_bbox_match_rate:.2%}")
        
        return report
