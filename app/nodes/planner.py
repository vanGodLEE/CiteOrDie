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
    
    system_prompt = """你是软件项目技术需求分析专家。我会给你一个文档的标题列表，你需要筛选出包含"技术需求"的标题。

## ⚠️ 什么是技术需求？
技术需求 = 具体的、可量化的、可验证的技术指标、参数、规格、标准

**技术需求示例**：
- "响应时间不超过2秒" ✅ 这是技术需求
- "系统要快速响应" ❌ 这只是泛泛描述
- "支持1000并发用户" ✅ 这是技术需求  
- "需要有用户管理功能" ❌ 这是功能描述

## ✅ 应该选择的标题（包含技术需求）

### 1. 技术指标类
- 性能指标、性能要求、性能参数（响应时间、并发数、吞吐量、TPS/QPS）
- 可用性指标、可靠性要求（可用性99.9%、MTBF、RTO/RPO）
- 容量要求、存储容量、数据量（支持XX万用户、XX GB数据）

### 2. 技术规范类
- 技术架构、系统架构、架构要求（微服务、SOA、三层架构）
- 接口规范、API规范、数据接口（RESTful、WebService、协议规范）
- 安全规范、安全标准（等保三级、SSL/TLS版本、加密算法）
- 开发规范、代码规范、技术标准（编码规范、技术栈要求）

### 3. 技术环境类
- 运行环境、部署环境、系统环境（操作系统版本、JDK版本、数据库版本）
- 服务器配置、硬件配置（CPU核数、内存大小、网络带宽）
- 兼容性要求（浏览器版本、移动端适配、多终端支持）
- 数据库要求（MySQL 8.0+、Oracle 19c、Redis集群）

### 4. 技术能力类
- 扩展性要求、伸缩性要求（支持横向扩展、弹性伸缩）
- 集成能力、对接能力（对接XX系统、集成XX平台）
- 容灾备份、高可用（双机热备、异地容灾、数据备份策略）

## ❌ 应该过滤的标题（不选择）

### 1. 功能描述类（不是技术需求）
- 功能清单、业务功能、功能模块（只描述做什么，不涉及技术指标）
- 用户管理、权限管理、流程管理（纯功能名称）

### 2. 商务资质类
- 企业资质、营业执照、业绩要求、人员资质、财务状况

### 3. 合同服务类
- 合同条款、付款方式、售后服务、培训计划、质保期限

### 4. 形式内容类
- 前言、须知、封面、声明、附件、投标人须知

## 🎯 判断标准

选择标题时，问自己：
1. ❓ 这个章节会包含具体的技术指标或参数吗？
2. ❓ 这个章节会规定具体的技术规范或标准吗？
3. ❓ 这个章节会明确技术环境或配置要求吗？

如果答案是"是"，就选择；如果是"可能有功能描述"，就过滤。

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
