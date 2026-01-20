"""
集成测试 - 验证完整工作流

使用Mock数据测试整个招标分析流程
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from app.core.graph import create_tender_analysis_graph
from app.core.states import TenderAnalysisState


def test_workflow_with_mock_data():
    """测试使用Mock数据的完整工作流"""
    
    logger.info("========================================")
    logger.info("开始集成测试：招标分析完整工作流")
    logger.info("========================================\n")
    
    # 创建初始状态
    initial_state = TenderAnalysisState(
        pdf_path="tests/mock_data/sample_tender.json",  # Mock数据路径
        use_mock=True,
        content_list=[],
        markdown="",
        toc=[],
        target_sections=[],
        requirements=[],
        final_matrix=[],
        processing_start_time=None,
        processing_end_time=None,
        error_message=None
    )
    
    try:
        # 创建工作流图
        logger.info("步骤1: 创建LangGraph工作流图")
        graph = create_tender_analysis_graph()
        logger.info("✓ 工作流图创建成功\n")
        
        # 执行工作流
        logger.info("步骤2: 执行工作流")
        result = graph.invoke(initial_state)
        logger.info("✓ 工作流执行完成\n")
        
        # 验证结果
        logger.info("步骤3: 验证结果")
        
        final_matrix = result.get("final_matrix", [])
        logger.info(f"✓ 提取到 {len(final_matrix)} 条需求\n")
        
        # 打印前5条需求作为示例
        logger.info("前5条需求示例：")
        for i, req in enumerate(final_matrix[:5], 1):
            logger.info(f"\n需求 #{i}:")
            logger.info(f"  ID: {req.matrix_id}")
            logger.info(f"  重要性: {req.importance}")
            logger.info(f"  章节: {req.section_id} - {req.section_title}")
            logger.info(f"  摘要: {req.summary}")
            logger.info(f"  页码: {req.page_number}")
            logger.info(f"  置信度: {req.confidence}")
        
        # 保存结果到JSON文件
        output_path = Path("tests/output_result.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                [req.dict() for req in final_matrix],
                f,
                ensure_ascii=False,
                indent=2
            )
        logger.info(f"\n✓ 结果已保存到: {output_path}")
        
        logger.info("\n========================================")
        logger.info("集成测试完成！工作流运行正常 ✓")
        logger.info("========================================")
        
        return True
        
    except Exception as e:
        logger.error(f"\n✗ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_workflow_with_mock_data()
    sys.exit(0 if success else 1)
