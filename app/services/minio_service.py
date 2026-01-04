"""
MinIO对象存储服务

负责PDF文件的上传、下载和管理
"""

from typing import Optional
from pathlib import Path
from datetime import datetime
from minio import Minio
from minio.error import S3Error
from loguru import logger

from app.core.config import settings


class MinioService:
    """MinIO对象存储服务"""
    
    def __init__(self):
        """初始化MinIO客户端"""
        try:
            self.client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            self.bucket_name = settings.minio_bucket
            
            # 确保bucket存在
            self._ensure_bucket_exists()
            
            logger.info(f"✓ MinIO服务初始化完成: {settings.minio_endpoint}/{self.bucket_name}")
        except Exception as e:
            logger.error(f"MinIO初始化失败: {e}")
            logger.error(
                "请检查配置：\n"
                "  1. MINIO_ENDPOINT应该是S3 API端口（通常是9000），而不是Web Console端口（通常是9001）\n"
                "  2. 当前配置: {}\n"
                "  3. 尝试将端口从19001改为19000，或咨询MinIO管理员获取正确的API端口"
                .format(settings.minio_endpoint)
            )
            raise
    
    def _ensure_bucket_exists(self):
        """确保bucket存在，如果不存在则创建"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"✓ 创建MinIO bucket: {self.bucket_name}")
            else:
                logger.debug(f"MinIO bucket已存在: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"检查/创建bucket失败: {e}")
            raise
    
    def upload_pdf(self, file_path: str, task_id: str) -> str:
        """
        上传PDF文件到MinIO
        
        Args:
            file_path: 本地PDF文件路径
            task_id: 任务ID（用于生成对象名称）
            
        Returns:
            MinIO中的对象URL
        """
        try:
            # 生成对象名称：task_id/原文件名_时间戳.pdf
            file_name = Path(file_path).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            object_name = f"{task_id}/{Path(file_name).stem}_{timestamp}.pdf"
            
            # 上传文件
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=file_path,
                content_type="application/pdf"
            )
            
            # 生成访问URL
            url = f"http://{settings.minio_endpoint}/{self.bucket_name}/{object_name}"
            
            logger.info(f"✓ PDF文件已上传到MinIO: {url}")
            return url
            
        except S3Error as e:
            logger.error(f"上传PDF到MinIO失败: {e}")
            raise Exception(f"MinIO上传失败: {str(e)}")
        except Exception as e:
            logger.error(f"上传PDF时发生错误: {e}")
            raise
    
    def get_pdf_url(self, task_id: str, expires_hours: int = 24) -> tuple[Optional[str], Optional[str]]:
        """
        根据task_id获取PDF的访问URL（预签名URL）
        
        Args:
            task_id: 任务ID
            expires_hours: URL有效期（小时），默认24小时
            
        Returns:
            tuple: (直接访问URL, Nginx代理URL)，如果不存在返回(None, None)
        """
        try:
            # 列出该task_id下的所有对象
            objects = self.client.list_objects(
                bucket_name=self.bucket_name,
                prefix=f"{task_id}/",
                recursive=True
            )
            
            # 获取第一个PDF文件
            for obj in objects:
                if obj.object_name.endswith('.pdf'):
                    # 生成预签名URL（临时访问链接）
                    from datetime import timedelta
                    direct_url = self.client.presigned_get_object(
                        bucket_name=self.bucket_name,
                        object_name=obj.object_name,
                        expires=timedelta(hours=expires_hours)
                    )
                    
                    # 生成Nginx代理URL
                    # 将内网地址替换为代理路径（保持签名参数不变）
                    nginx_url = self._convert_to_nginx_url(direct_url)
                    
                    logger.debug(f"生成预签名URL (直接): {direct_url[:100]}...")
                    logger.debug(f"生成预签名URL (代理): {nginx_url[:100]}...")
                    
                    return direct_url, nginx_url
            
            logger.warning(f"未找到task_id={task_id}的PDF文件")
            return None, None
            
        except S3Error as e:
            logger.error(f"从MinIO获取PDF URL失败: {e}")
            return None, None
        except Exception as e:
            logger.error(f"获取PDF URL时发生错误: {e}")
            return None, None
    
    def _convert_to_nginx_url(self, minio_url: str) -> str:
        """
        将Minio内网URL转换为Nginx代理URL
        
        Args:
            minio_url: Minio生成的预签名URL
            
        Returns:
            可通过Nginx访问的URL路径
        """
        import urllib.parse
        
        # 解析URL
        parsed = urllib.parse.urlparse(minio_url)
        
        # 提取路径和查询参数
        # 原始: http://192.168.100.219:19000/tender-pdf/task_id/file.pdf?X-Amz-...
        # 目标: /tender-minio/tender-pdf/task_id/file.pdf?X-Amz-...
        
        # 路径部分（去掉开头的/）
        path = parsed.path.lstrip('/')
        
        # 查询参数（保持不变，包含签名）
        query = parsed.query
        
        # 构建Nginx代理路径
        nginx_path = f"/tender-minio/{path}"
        if query:
            nginx_path = f"{nginx_path}?{query}"
        
        return nginx_path
    
    def download_pdf(self, object_name: str, local_path: str):
        """
        从MinIO下载PDF文件
        
        Args:
            object_name: MinIO中的对象名称
            local_path: 本地保存路径
        """
        try:
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=local_path
            )
            logger.info(f"✓ PDF文件已下载: {local_path}")
        except S3Error as e:
            logger.error(f"从MinIO下载PDF失败: {e}")
            raise Exception(f"MinIO下载失败: {str(e)}")
    
    def delete_pdf(self, task_id: str):
        """
        删除task_id下的所有PDF文件
        
        Args:
            task_id: 任务ID
        """
        try:
            # 列出该task_id下的所有对象
            objects = self.client.list_objects(
                bucket_name=self.bucket_name,
                prefix=f"{task_id}/",
                recursive=True
            )
            
            # 删除所有对象
            for obj in objects:
                self.client.remove_object(
                    bucket_name=self.bucket_name,
                    object_name=obj.object_name
                )
                logger.debug(f"已删除: {obj.object_name}")
            
            logger.info(f"✓ 已删除task_id={task_id}的所有文件")
            
        except S3Error as e:
            logger.error(f"从MinIO删除PDF失败: {e}")
            raise Exception(f"MinIO删除失败: {str(e)}")


# 全局单例
_minio_service: Optional[MinioService] = None


def get_minio_service() -> MinioService:
    """获取MinIO服务单例"""
    global _minio_service
    if _minio_service is None:
        _minio_service = MinioService()
    return _minio_service