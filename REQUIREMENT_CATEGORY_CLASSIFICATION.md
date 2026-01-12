# 需求类型分类功能

## 📋 概述

本功能在招标需求提取过程中，自动对每个需求进行类型分类，帮助用户快速识别哪些需求需要在技术/服务方案中详细响应，哪些只需要提供资质文件或商务文件即可。

## 🎯 需求类型定义

系统将需求分为6种类型：

### 1. **SOLUTION**（技术/服务方案）
**定义**: 必须在技术方案或服务方案中详细响应的需求

**包括**:
- 功能需求：系统功能、业务流程
- 技术需求：架构、技术选型、开发框架
- 性能需求：响应时间、并发量、可用性
- 质量需求：安全性、可维护性、可扩展性
- 部署需求：部署环境、服务器配置
- 实施需求：实施计划、人员投入、培训
- 服务需求：售后服务、运维支持、SLA
- 风险需求：风险控制、应急预案
- 交付物：需要交付的文档、代码、产品

**示例**:
- "系统需采用B/S架构"
- "响应时间不超过2秒"
- "需提供详细的实施方案"
- "需配备专职项目经理"

**应答位置**: 技术方案或服务方案正文

### 2. **QUALIFICATION**（资质/资格）
**定义**: 企业资质、证书、授权、业绩、财务、信誉、人员证书等

**包括**:
- 企业资质：ISO认证、行业资质、许可证
- 企业规模：注册资金、员工数量、办公面积
- 企业业绩：类似项目经验、客户案例
- 财务状况：财务报表、纳税证明
- 人员证书：项目经理证书、技术人员资格证
- 授权文件：厂商授权、代理授权

**示例**:
- "需具有ISO9001质量管理体系认证"
- "注册资金不少于500万元"
- "近三年内有类似项目业绩"
- "项目经理需持有PMP证书"

**应答位置**: 资质文件或商务文件（不需要在方案正文中逐条响应）

### 3. **BUSINESS**（商务条款）
**定义**: 报价、付款、税率、合同条款、投标有效期、交货期、保函等

**包括**:
- 报价：总价、分项报价、优惠
- 付款：付款方式、付款比例、付款节点
- 税率：含税价、税率说明
- 合同：合同条款、偏离表
- 时间：投标有效期、交货期、实施周期
- 保函：投标保证金、履约保证金

**示例**:
- "付款方式为分期付款"
- "投标有效期90天"
- "需缴纳履约保证金"

**应答位置**: 商务文件或报价文件

### 4. **FORMAT**（格式要求）
**定义**: 投标文件的格式、目录、装订、签章、页码、密封、递交方式等

**包括**:
- 文件格式：PDF、Word、纸质版
- 装订方式：胶装、活页、电子版
- 签章要求：公章、骑缝章、法人签字
- 目录要求：目录格式、页码编制
- 密封要求：密封袋、密封条、标识
- 递交方式：现场递交、邮寄、电子投标

**示例**:
- "投标文件需加盖公章"
- "需提供PDF和纸质版各一份"
- "需采用胶装方式装订"

**应答位置**: 按格式要求制作投标文件即可

### 5. **PROCESS**（流程要求）
**定义**: 招投标流程相关的要求

**包括**:
- 报名：报名时间、报名方式
- 澄清：澄清时间、答疑会议
- 开标：开标时间、开标地点
- 电子投标：CA证书、加密方式
- 保证金：缴纳时间、缴纳方式
- 其他流程：踏勘现场、资格预审

**示例**:
- "需在规定时间参加现场答疑"
- "需使用CA证书加密投标文件"
- "投标保证金需在开标前缴纳"

**应答位置**: 按流程要求执行即可

### 6. **OTHER**（其他/不确定）
**定义**: 不确定或难以归类的需求，需要人工确认

**包括**:
- 表述不清的需求
- 可能属于多个类别的需求
- 需要进一步明确的需求

**示例**:
- "需提供某方案说明"（不明确是技术还是商务）
- 新出现的特殊要求

**处理方式**: 标记为OTHER，由人工后续确认和调整

## 📝 数据结构

### RequirementItem 模型
```python
class RequirementItem(BaseModel):
    matrix_id: str              # 需求ID
    requirement: str            # 需求内容
    original_text: str          # 原文
    section_id: str             # 章节编号
    section_title: str          # 章节标题
    page_number: int            # 页码
    category: str               # 需求类型（新增）⭐
    response_suggestion: str    # 应答方向
    risk_warning: str           # 风险提示
    notes: str                  # 备注
```

### 数据库表结构
```sql
ALTER TABLE requirements 
ADD COLUMN category VARCHAR(20) DEFAULT 'OTHER';
```

## 🔄 工作流程

```
PDF文档
  ↓
PageIndex解析（生成结构树）
  ↓
遍历叶子节点
  ↓
LLM提取需求 + 分类判断 ⭐
  ↓
生成RequirementItem（包含category）
  ↓
保存到数据库
  ↓
API返回（包含category字段）
```

## 🤖 LLM 分类逻辑

### Prompt 要点
```python
"""
## 需求类型分类

为每个提取的需求判断类型（category字段），必须选择以下之一：

1. **SOLUTION**（技术/服务方案）
   - 必须在技术方案或服务方案中详细响应的需求
   - 包括：功能、性能、架构、技术选型、实施方法、人员投入、
           保障措施、SLA、风险控制、交付物等
   - 示例："系统需采用B/S架构"、"响应时间不超过2秒"

2. **QUALIFICATION**（资质/资格）
   - 企业资质、证书、授权、业绩、财务、信誉、人员证书等
   - 通常放在资质文件或商务文件中
   - 示例："需提供ISO9001证书"、"注册资金不少于500万"

3. **BUSINESS**（商务条款）
   - 报价、付款、税率、合同条款、投标有效期、交货期、保函等
   - 示例："付款方式为分期付款"、"投标有效期90天"

4. **FORMAT**（格式要求）
   - 投标文件的格式、目录、装订、签章、页码、密封、递交方式等
   - 示例："投标文件需加盖公章"、"需提供PDF和纸质版"

5. **PROCESS**（流程要求）
   - 招投标流程相关（报名、澄清、答疑、开标、电子标、CA、保证金等）
   - 示例："需在规定时间参加现场答疑"

6. **OTHER**（其他/不确定）
   - 不确定或难以归类的需求
   - 需要人工确认的情况

**分类判断原则**：
- 优先判断是否需要在技术/服务方案中响应（SOLUTION）
- 资质类、商务类、格式类比较明确，容易判断
- 如果不确定，标记为OTHER，由人工后续确认
"""
```

### 分类示例

#### 示例1: SOLUTION
```json
{
  "requirement": "系统需支持1000个并发用户",
  "category": "SOLUTION",
  "response_suggestion": "在技术方案中说明系统架构设计和负载均衡方案"
}
```

#### 示例2: QUALIFICATION
```json
{
  "requirement": "需具有ISO9001证书",
  "category": "QUALIFICATION",
  "response_suggestion": "在资质文件中提供ISO9001证书复印件"
}
```

#### 示例3: BUSINESS
```json
{
  "requirement": "分三期付款：预付30%、验收60%、质保10%",
  "category": "BUSINESS",
  "response_suggestion": "在商务报价中明确付款节点和金额"
}
```

## 🗄️ 数据库迁移

### 执行迁移
```bash
python scripts/migrate_add_category.py
```

### 手动SQL
```sql
-- 添加 category 字段
ALTER TABLE requirements 
ADD COLUMN category VARCHAR(20) DEFAULT 'OTHER';

-- 验证
SELECT category, COUNT(*) 
FROM requirements 
GROUP BY category;
```

## 📊 API 返回示例

### GET /api/task/{task_id}
```json
{
  "task_id": "abc-123",
  "status": "completed",
  "matrix": [
    {
      "matrix_id": "3.1-REQ-001",
      "requirement": "系统需采用B/S架构",
      "original_text": "系统需采用B/S架构...",
      "section_id": "3.1",
      "section_title": "技术要求",
      "page_number": 15,
      "category": "SOLUTION",  ⭐
      "response_suggestion": "在技术方案中说明架构设计",
      "risk_warning": "需确保浏览器兼容性",
      "notes": "关键技术要求"
    },
    {
      "matrix_id": "2.1-REQ-001",
      "requirement": "需具有ISO9001质量管理体系认证",
      "category": "QUALIFICATION",  ⭐
      "response_suggestion": "在资质文件中提供证书复印件",
      ...
    }
  ]
}
```

## 📈 使用场景

### 场景1: 快速筛选需要响应的需求
```python
# 筛选需要在技术方案中响应的需求
solution_reqs = [req for req in matrix if req["category"] == "SOLUTION"]
```

### 场景2: 按类型统计
```python
# 统计各类型需求数量
from collections import Counter
categories = Counter(req["category"] for req in matrix)
print(categories)
# {'SOLUTION': 35, 'QUALIFICATION': 8, 'BUSINESS': 5, 'FORMAT': 3, 'PROCESS': 2}
```

### 场景3: 生成分类报告
```python
# 按类型分组展示
for category in ["SOLUTION", "QUALIFICATION", "BUSINESS", "FORMAT", "PROCESS", "OTHER"]:
    reqs = [req for req in matrix if req["category"] == category]
    print(f"\n{category}: {len(reqs)}条")
    for req in reqs:
        print(f"  - {req['requirement']}")
```

## ✅ 验证测试

### 测试用例
1. **创建新任务**: 验证需求自动分类
2. **查询任务**: 验证category字段正确返回
3. **Excel导出**: 验证分类信息包含在导出文件中
4. **旧任务兼容**: 验证已有需求默认为OTHER

### 验证步骤
```bash
# 1. 执行数据库迁移
python scripts/migrate_add_category.py

# 2. 重启应用
# 停止服务 → 启动服务

# 3. 上传新文件进行分析
POST /api/analyze

# 4. 查询结果
GET /api/task/{task_id}

# 5. 检查category字段
{
  "matrix": [
    {"category": "SOLUTION", ...},
    {"category": "QUALIFICATION", ...}
  ]
}
```

## 🎯 预期效果

### 分类准确度
- **SOLUTION**: 95%+ 准确度（最重要的类型）
- **QUALIFICATION**: 90%+ 准确度（比较明确）
- **BUSINESS**: 90%+ 准确度（比较明确）
- **FORMAT**: 85%+ 准确度
- **PROCESS**: 85%+ 准确度
- **OTHER**: 用于不确定的情况（需人工确认）

### 业务价值
1. **提高效率**: 快速识别需要在方案中响应的需求
2. **规范投标**: 明确各类需求的应答位置
3. **降低风险**: 避免遗漏关键需求或放错位置
4. **便于管理**: 按类型统计和分析需求

## 🔧 相关文件

- [`app/core/states.py`](app/core/states.py) - RequirementItem模型定义
- [`app/db/models.py`](app/db/models.py) - 数据库模型
- [`app/db/repositories.py`](app/db/repositories.py) - 数据访问层
- [`app/nodes/pageindex_enricher.py`](app/nodes/pageindex_enricher.py) - 需求提取和分类逻辑
- [`app/api/async_analyze.py`](app/api/async_analyze.py) - API返回
- [`scripts/migrate_add_category.py`](scripts/migrate_add_category.py) - 数据库迁移脚本

## 📚 总结

本功能通过LLM智能判断，为每个需求自动分类，帮助用户：
- ✅ 快速识别哪些需求需要在技术/服务方案中详细响应
- ✅ 明确各类需求的应答位置
- ✅ 提高投标文件制作效率
- ✅ 降低遗漏风险

**核心价值**: 让AI不仅提取需求，还能智能分类，真正实现智能化招标分析！