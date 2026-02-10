"""
任务清理服务

用于删除任务及其相关的所有文件和数据：
1. 数据库记录（task, logs, sections, clauses）
2. MinIO中的PDF文件
3. 本地PDF文件（temp/uploads）
4. MinerU输出目录
5. 日志文件
6. middle_json文件
"""

import shutil
from pathlib import Path
from typing import Optional
from loguru import logger


class TaskCleanupService:
    """任务清理服务"""
    
    @staticmethod
    def delete_local_pdf(pdf_path: str) -> bool:
        """
        删除本地PDF文件
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            是否成功删除
        """
        try:
            if not pdf_path:
                return True
            
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                pdf_file.unlink()
                logger.info(f"✓ 已删除本地PDF: {pdf_path}")
                return True
            else:
                logger.debug(f"本地PDF不存在: {pdf_path}")
                return True
        except Exception as e:
            logger.error(f"删除本地PDF失败: {e}")
            return False
    
    @staticmethod
    def delete_mineru_output(task_id: str, pdf_name: str) -> bool:
        """
        删除MinerU输出目录
        
        Args:
            task_id: 任务ID
            pdf_name: PDF文件名（不含扩展名）
            
        Returns:
            是否成功删除
        """
        try:
            mineru_base = Path("mineru_output")
            
            # 方式1：按task_id查找
            task_dir = mineru_base / task_id
            if task_dir.exists():
                shutil.rmtree(task_dir)
                logger.info(f"✓ 已删除MinerU输出目录: {task_dir}")
                return True
            
            # 方式2：遍历查找包含该PDF的目录
            if mineru_base.exists():
                for task_folder in mineru_base.iterdir():
                    if task_folder.is_dir():
                        pdf_folder = task_folder / pdf_name
                        if pdf_folder.exists():
                            shutil.rmtree(task_folder)
                            logger.info(f"✓ 已删除MinerU输出目录: {task_folder}")
                            return True
            
            logger.debug(f"MinerU输出目录不存在: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除MinerU输出目录失败: {e}")
            return False
    
    @staticmethod
    def delete_middle_json(task_id: str, pdf_name: str) -> bool:
        """
        删除middle_json文件
        
        Args:
            task_id: 任务ID
            pdf_name: PDF文件名（不含扩展名）
            
        Returns:
            是否成功删除
        """
        try:
            middle_json_dir = Path("middle_json")
            if not middle_json_dir.exists():
                return True
            
            # 查找所有相关的middle_json文件
            deleted_count = 0
            for json_file in middle_json_dir.glob(f"{pdf_name}_*.json"):
                json_file.unlink()
                deleted_count += 1
                logger.debug(f"✓ 已删除middle_json: {json_file.name}")
            
            if deleted_count > 0:
                logger.info(f"✓ 已删除 {deleted_count} 个middle_json文件")
            
            return True
            
        except Exception as e:
            logger.error(f"删除middle_json失败: {e}")
            return False
    
    @staticmethod
    def delete_log_files(pdf_name: str) -> bool:
        """
        删除日志文件
        
        Args:
            pdf_name: PDF文件名（含扩展名）
            
        Returns:
            是否成功删除
        """
        try:
            logs_dir = Path("logs")
            if not logs_dir.exists():
                return True
            
            # 查找所有相关的日志文件
            deleted_count = 0
            for log_file in logs_dir.glob(f"{pdf_name}_*.json"):
                log_file.unlink()
                deleted_count += 1
                logger.debug(f"✓ 已删除日志文件: {log_file.name}")
            
            if deleted_count > 0:
                logger.info(f"✓ 已删除 {deleted_count} 个日志文件")
            
            return True
            
        except Exception as e:
            logger.error(f"删除日志文件失败: {e}")
            return False
    
    @staticmethod
    def delete_minio_file(task_id: str) -> bool:
        """
        删除MinIO中的PDF文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功删除
        """
        try:
            from app.services.object_storage import get_object_storage_service

            storage = get_object_storage_service()
            success = storage.delete_pdf(task_id)
            
            if success:
                logger.info(f"✓ 已删除MinIO文件: {task_id}")
            else:
                logger.warning(f"MinIO文件删除失败或不存在: {task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"删除MinIO文件失败: {e}")
            return False
    
    @staticmethod
    def cleanup_task(
        task_id: str,
        pdf_path: Optional[str] = None,
        file_name: Optional[str] = None
    ) -> dict:
        """
        清理任务的所有相关文件
        
        Args:
            task_id: 任务ID
            pdf_path: PDF文件路径
            file_name: 文件名
            
        Returns:
            清理结果字典
        """
        logger.info(f"=== 开始清理任务: {task_id} ===")
        
        results = {
            "task_id": task_id,
            "local_pdf": False,
            "minio_file": False,
            "mineru_output": False,
            "middle_json": False,
            "log_files": False
        }
        
        # 提取PDF文件名（不含扩展名）
        pdf_name = None
        if file_name:
            pdf_name = Path(file_name).stem
        elif pdf_path:
            pdf_name = Path(pdf_path).stem
        
        # 1. 删除本地PDF
        if pdf_path:
            results["local_pdf"] = TaskCleanupService.delete_local_pdf(pdf_path)
        
        # 2. 删除MinIO文件
        results["minio_file"] = TaskCleanupService.delete_minio_file(task_id)
        
        # 3. 删除MinerU输出
        if pdf_name:
            results["mineru_output"] = TaskCleanupService.delete_mineru_output(task_id, pdf_name)
        
        # 4. 删除middle_json
        if pdf_name:
            results["middle_json"] = TaskCleanupService.delete_middle_json(task_id, pdf_name)
        
        # 5. 删除日志文件
        if file_name:
            results["log_files"] = TaskCleanupService.delete_log_files(file_name)
        
        success_count = sum(1 for v in results.values() if v and v != task_id)
        logger.success(f"=== 任务清理完成: {task_id}，成功 {success_count}/5 项 ===")
        
        return results
