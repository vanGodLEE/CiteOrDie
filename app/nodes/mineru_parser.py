"""
MinerU解析节点

在PageIndex解析之后，使用MinerU完整解析PDF文档
"""

from typing import Dict, Any
from loguru import logger
from app.core.states import TenderAnalysisState
from app.services.mineru_service import get_mineru_service
from app.api.async_tasks import TaskManager


def mineru_parser_node(state: TenderAnalysisState) -> Dict[str, Any]:
    """
    MinerU解析节点
    
    输入:
    - state["pdf_path"]: PDF文件路径
    - state["task_id"]: 任务ID
    
    输出:
    - state["mineru_result"]: MinerU解析结果
    - state["mineru_content_list"]: 内容列表
    - state["mineru_output_dir"]: 输出目录
    
    工作流程:
    1. 调用MinerU服务解析PDF
    2. 将解析结果存入State
    3. 更新任务进度
    """
    pdf_path = state.get("pdf_path")
    task_id = state.get("task_id")
    
    if not pdf_path:
        logger.error("未找到pdf_path，无法调用MinerU")
        return {
            "error_message": "缺少PDF文件路径",
            "mineru_result": None,
            "mineru_content_list": [],
            "mineru_output_dir": None
        }
    
    # 更新任务进度
    if task_id:
        TaskManager.log_progress(
            task_id,
            "正在使用MinerU解析PDF文档（包含图片、表格）...",
            15
        )
    
    try:
        logger.info(f"开始调用MinerU解析PDF: {pdf_path}")
        
        # 调用MinerU服务
        mineru_service = get_mineru_service()
        result = mineru_service.parse_pdf(
            pdf_path=pdf_path,
            task_id=task_id or "default"
        )
        
        if not result:
            error_msg = "MinerU解析失败，无法获取文档内容"
            logger.error(error_msg)
            return {
                "error_message": error_msg,
                "mineru_result": None,
                "mineru_content_list": [],
                "mineru_output_dir": None
            }
        
        # 提取关键信息
        content_list = result.get("content_list", [])
        output_dir = result.get("output_dir")
        type_counts = result.get("type_counts", {})
        
        logger.info(f"✓ MinerU解析完成")
        logger.info(f"  - 总内容项: {len(content_list)}")
        logger.info(f"  - 文本: {type_counts.get('text', 0)}")
        logger.info(f"  - 列表: {type_counts.get('list', 0)}")
        logger.info(f"  - 图片: {type_counts.get('image', 0)}")
        logger.info(f"  - 表格: {type_counts.get('table', 0)}")
        logger.info(f"  - 输出目录: {output_dir}")
        
        # 更新任务进度
        if task_id:
            TaskManager.log_progress(
                task_id,
                f"MinerU解析完成，共解析 {len(content_list)} 个内容项",
                20
            )
        
        return {
            "mineru_result": result,
            "mineru_content_list": content_list,
            "mineru_output_dir": output_dir
        }
        
    except Exception as e:
        error_msg = f"MinerU解析异常: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)
        
        return {
            "error_message": error_msg,
            "mineru_result": None,
            "mineru_content_list": [],
            "mineru_output_dir": None
        }