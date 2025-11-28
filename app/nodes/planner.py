"""
Planner节点 - 战略规划

负责分析文档目录，识别包含需求的关键章节，过滤无关内容
这是智能体的"大脑"
"""

from typing import List
from pydantic import BaseModel
from loguru import logger

from app.core.states import TenderAnalysisState, TOCItem, SectionPlan
from app.services.llm_service import llm_service


# Pydantic模型用于Structured Output
class HeaderCandidate(BaseModel):
    """标题候选（用于发给LLM筛选）"""
    text: str
    index: int


class FilteredHeaders(BaseModel):
    """LLM筛选后的标题列表"""
    headers: List[HeaderCandidate]


def planner_node(state: TenderAnalysisState) -> dict:
    """
    Planner节点 - 智能章节筛选
    
    新逻辑（基于MinerU的text_level标记）：
    1. 从content_list中提取所有text_level=1的标题
    2. 将标题列表发给LLM筛选
    3. LLM返回包含需求的标题
    4. 为每个标题创建SectionPlan
    
    Args:
        state: 全局状态
        
    Returns:
        更新后的状态字典
    """
    logger.info("====== Planner节点开始执行 ======")
    
    # 更新进度：开始分析标题
    task_id = state.get("task_id")
    if task_id:
        from app.api.async_tasks import TaskManager
        TaskManager.update_task(task_id, progress=15, message="正在识别文档标题...")
    
    content_list = state["content_list"]
    
    # 步骤1: 提取所有text_level=1的标题
    header_candidates = []
    for idx, block in enumerate(content_list):
        if block.get("text_level") == 1:
            text = block.get("text", "").strip()
            # 过滤掉太短或无意义的标题
            if len(text) < 2:
                continue
            header_candidates.append(HeaderCandidate(
                text=text,
                index=idx
            ))
    
    if not header_candidates:
        logger.warning("未找到任何标题（text_level=1），无法进行章节规划")
        return {"target_sections": []}
    
    logger.info(f"找到 {len(header_candidates)} 个标题候选")
    logger.debug(f"前10个标题示例: {[h.text[:30] for h in header_candidates[:10]]}")
    
    # 简单预过滤：排除明显无关的标题
    exclude_keywords = ["封面", "声明", "目录", "页码", "PAGE", "第 页", "投标人", "盖章", "签字", "日期", "年 月 日"]
    filtered = []
    for h in header_candidates:
        if not any(kw in h.text for kw in exclude_keywords):
            filtered.append(h)
    
    if len(filtered) < len(header_candidates):
        logger.info(f"预过滤排除 {len(header_candidates) - len(filtered)} 个无关标题，剩余 {len(filtered)} 个")
        header_candidates = filtered
    
    if not header_candidates:
        logger.warning("预过滤后没有剩余标题")
        return {"target_sections": []}
    
    # 步骤2: 分批筛选标题（每批最多30个）
    BATCH_SIZE = 30
    all_filtered_headers = []
    
    # 计算需要多少批
    num_batches = (len(header_candidates) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(f"标题总数: {len(header_candidates)}，分{num_batches}批处理，每批最多{BATCH_SIZE}个")
    
    system_prompt = """你是招标文件分析专家。我会给你一个文档的标题列表，你需要筛选出包含"招标需求"的标题。

## ⚠️ 什么是招标需求？
招标需求 = 招标方对软件系统、项目实施、服务交付的所有要求

包括但不限于：功能需求、技术需求、性能需求、质量需求、交付需求、服务需求等

## ✅ 应该选择的标题（包含招标需求）

### 1. 功能需求类
- 功能要求、功能清单、功能模块、业务功能
- 用户管理、权限管理、数据管理、流程管理
- 系统功能、核心功能、业务流程

### 2. 技术需求类
- 技术架构、系统架构、技术方案、技术路线
- 技术指标、性能指标、性能要求（响应时间、并发数、可用性）
- 接口规范、API要求、数据接口、系统对接
- 安全要求、安全标准、数据安全、信息安全
- 开发规范、技术规范、代码规范

### 3. 运行环境类
- 运行环境、部署环境、系统环境
- 服务器要求、硬件配置、网络要求
- 数据库要求、中间件要求
- 兼容性要求、浏览器支持

### 4. 质量需求类
- 质量要求、验收标准、测试要求
- 可靠性、稳定性、可维护性
- 文档要求、交付物要求

### 5. 实施服务类
- 实施方案、实施计划、项目计划
- 培训要求、培训方案（针对系统使用培训）
- 售后服务、运维服务、技术支持
- 数据迁移、系统部署

## ❌ 应该过滤的标题（不选择）

### 1. 商务资质类（对投标人的要求）
- 企业资质、营业执照、业绩要求、人员资质
- 财务状况、注册资金、资质证明

### 2. 合同条款类
- 合同条款、付款方式、违约责任
- 知识产权归属、保密协议

### 3. 投标形式类
- 前言、须知、封面、声明、目录
- 投标人须知、投标文件格式、装订要求

## 🎯 判断标准（关键区分）

✅ **对系统的要求** → 选择
- "系统需要提供用户管理功能" ✅
- "系统响应时间<2秒" ✅
- "需要提供培训服务" ✅

❌ **对投标人的要求** → 过滤
- "投标人需具有软件企业资质" ❌
- "投标人需提供营业执照" ❌
- "投标人注册资金≥1000万" ❌

## 输出要求

返回筛选后的标题列表，保持原有的text和index字段，不要修改。"""
    
    # 分批处理
    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(header_candidates))
        batch = header_candidates[start_idx:end_idx]
        
        logger.info(f"处理第 {batch_idx + 1}/{num_batches} 批标题 (共{len(batch)}个)")
        
        # 构造标题列表字符串
        headers_str = "\n".join([f"{i+1}. {h.text} (index: {h.index})" for i, h in enumerate(batch)])
        
        user_prompt = f"""以下是文档中的一批标题（第{batch_idx+1}批，共{len(batch)}个）：

{headers_str}

请筛选出可能包含需求的标题，返回它们的text和index。"""
        
        # 调用LLM进行筛选
        try:
            result = llm_service.structured_completion(
                messages=[
                    llm_service.create_system_message(system_prompt),
                    llm_service.create_user_message(user_prompt)
                ],
                response_model=FilteredHeaders,
                temperature=0.1
            )
            
            batch_filtered = result.headers
            logger.info(f"第{batch_idx+1}批筛选结果: {len(batch_filtered)}/{len(batch)} 个标题被选中")
            all_filtered_headers.extend(batch_filtered)
            
        except Exception as e:
            logger.error(f"第{batch_idx+1}批处理失败: {e}")
            # 继续处理下一批
            continue
    
    filtered_headers = all_filtered_headers
    logger.info(f"所有批次处理完成，总共筛选出 {len(filtered_headers)} 个关键标题")
    
    # 更新进度：标题筛选完成
    if task_id:
        TaskManager.update_task(task_id, progress=30, message=f"已筛选出 {len(filtered_headers)} 个技术需求章节，正在准备提取...")
    
    # 输出筛选结果
    for i, h in enumerate(filtered_headers[:10]):  # 只显示前10个
        logger.debug(f"  筛选结果 {i+1}: {h.text}")
    
    if not filtered_headers:
        logger.warning("LLM未筛选出任何关键标题")
        return {"target_sections": []}
    
    # 步骤3: 为每个筛选出的标题创建SectionPlan
    try:
        target_sections = []
        for i, header in enumerate(filtered_headers):
            page_idx = content_list[header.index].get("page_idx", 0)
            target_sections.append(SectionPlan(
                section_id=f"SEC_{header.index}",
                title=header.text,
                reason="LLM识别为包含需求的章节",
                priority=i + 1,  # 按顺序赋予优先级
                start_page=page_idx + 1,  # 转为1-based
                start_index=header.index  # 记录起始索引
            ))
        
        logger.info(f"成功创建 {len(target_sections)} 个章节计划")
        for sec in target_sections[:10]:  # 只显示前10个
            logger.debug(f"  - {sec.section_id}: {sec.title} (页{sec.start_page})")
        
        return {"target_sections": target_sections}
        
    except Exception as e:
        logger.error(f"创建SectionPlan失败: {e}")
        raise
