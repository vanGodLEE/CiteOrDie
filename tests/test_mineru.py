"""
MinerU独立测试脚本

用于测试MinerU是否正确安装和配置
"""

import sys
import subprocess
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def test_mineru_command():
    """测试MinerU命令是否可用"""
    logger.info("========================================")
    logger.info("测试1: 检查MinerU命令是否可用")
    logger.info("========================================\n")
    
    try:
        result = subprocess.run(
            ["mineru", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.info(f"✓ MinerU命令可用")
            logger.info(f"版本信息: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"✗ MinerU命令执行失败")
            logger.error(f"错误: {result.stderr}")
            return False
            
    except FileNotFoundError:
        logger.error("✗ 找不到mineru命令")
        logger.error("请确保已安装MinerU并配置到PATH")
        logger.error("安装命令: pip install -U mineru[core]")
        return False
    except Exception as e:
        logger.error(f"✗ 检查MinerU命令时出错: {e}")
        return False


def test_mineru_parsing(pdf_path: str = None):
    """测试MinerU解析功能"""
    logger.info("\n========================================")
    logger.info("测试2: 测试MinerU解析PDF")
    logger.info("========================================\n")
    
    # 如果没有指定PDF，尝试使用上传的测试文件
    if pdf_path is None:
        temp_dir = Path("temp")
        if temp_dir.exists():
            pdf_files = list(temp_dir.glob("*.pdf"))
            if pdf_files:
                pdf_path = str(pdf_files[0])
                logger.info(f"使用测试文件: {pdf_path}")
            else:
                logger.warning("temp目录下没有PDF文件")
                return False
        else:
            logger.warning("temp目录不存在")
            return False
    
    if not Path(pdf_path).exists():
        logger.error(f"✗ PDF文件不存在: {pdf_path}")
        return False
    
    # 创建测试输出目录
    output_dir = Path("temp/mineru_test_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        command = ["mineru", "-p", pdf_path, "-o", str(output_dir)]
        logger.info(f"执行命令: {' '.join(command)}")
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120  # 2分钟超时
        )
        
        logger.info(f"\n返回码: {result.returncode}")
        
        if result.stdout:
            logger.info(f"标准输出:\n{result.stdout}")
        
        if result.stderr:
            logger.warning(f"错误输出:\n{result.stderr}")
        
        if result.returncode != 0:
            logger.error("✗ MinerU解析失败")
            return False
        
        # 检查输出文件
        logger.info(f"\n输出目录内容 ({output_dir}):")
        found_files = []
        for item in output_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(output_dir)
                found_files.append(str(rel_path))
                logger.info(f"  - {rel_path} ({item.stat().st_size} bytes)")
        
        # 查找content_list.json
        content_list_files = [f for f in found_files if "content_list.json" in f]
        
        if content_list_files:
            logger.info(f"\n✓ 找到content_list文件: {content_list_files[0]}")
            
            # 读取并显示前几个内容块
            import json
            content_list_path = output_dir / content_list_files[0]
            with open(content_list_path, "r", encoding="utf-8") as f:
                content_list = json.load(f)
            
            logger.info(f"✓ content_list包含 {len(content_list)} 个内容块")
            logger.info(f"\n前3个内容块示例:")
            for i, block in enumerate(content_list[:3], 1):
                logger.info(f"  块#{i}: type={block.get('type')}, text={block.get('text', '')[:50]}...")
            
            return True
        else:
            logger.error("✗ 未找到content_list.json文件")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("✗ MinerU解析超时（>2分钟）")
        return False
    except Exception as e:
        logger.error(f"✗ 测试MinerU解析时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    logger.info("MinerU测试开始\n")
    
    # 测试1: 命令可用性
    command_ok = test_mineru_command()
    
    if not command_ok:
        logger.error("\n❌ MinerU命令不可用，请先安装MinerU")
        logger.info("\n安装步骤:")
        logger.info("1. pip install magic-pdf")
        logger.info("2. 或者使用uv: uv pip install magic-pdf")
        return False
    
    # 测试2: 解析功能
    parsing_ok = test_mineru_parsing()
    
    if not parsing_ok:
        logger.error("\n❌ MinerU解析测试失败")
        return False
    
    logger.info("\n========================================")
    logger.info("✓ 所有测试通过！MinerU工作正常")
    logger.info("========================================")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
