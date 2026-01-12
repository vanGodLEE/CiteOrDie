# MinerU集成改造 - 阶段2完成报告

## ✅ 阶段2：标题模糊匹配算法实现 - 已完成

**完成时间**: 2026-01-07  
**状态**: ✅ 完成

---

## 📋 已完成任务

### 1. 标题匹配核心算法
**文件**: [`app/utils/title_matcher.py`](app/utils/title_matcher.py)

**核心功能**:

#### 1.1 标题归一化
```python
TitleMatcher.normalize_title(title: str) -> str
```
- 转小写
- 移除所有空格
- 移除常见标点符号（保留§等特殊符号）

**示例**:
```python
"第二章 系统建设要求" → "第二章系统建设要求"
"§2.1. 基础功能部分" → "§21基础功能部分"
```

#### 1.2 标题包含判断
```python
TitleMatcher.is_title_contained(
    target_title: str,
    content_text: str,
    similarity_threshold: float = 0.85
) -> bool
```

**匹配策略**:
1. **精确包含**: 归一化后的target在content中
2. **模糊匹配**: 使用SequenceMatcher计算相似度≥阈值

**解决的问题**:
- ✅ `"第二章 系统建设要求"` 匹配 `"第二章系统建设要求"`
- ✅ `"§2.1. 基础功能部分"` 匹配在 `"§2.1. 基础功能部分§2.1.1. 企业用户"`
- ✅ 容忍标点、空格差异

#### 1.3 在content_list中查找标题
```python
TitleMatcher.find_title_in_content_list(
    target_title: str,
    content_list: List[Dict],
    page_range: Optional[Tuple[int, int]] = None
) -> Optional[int]
```

**功能**:
- 在MinerU解析的content_list中查找标题
- 支持页面范围过滤
- 自动提取不同type的文本（text、list、image、table）

**支持的content类型**:
- `text`: 直接使用text字段
- `list`: 拼接list_items
- `image`: 使用image_caption（如果有）
- `table`: 使用table_caption（如果有）

#### 1.4 根据标题范围提取内容
```python
TitleMatcher.find_content_range_by_titles(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict],
    page_range: Optional[Tuple[int, int]] = None
) -> List[Dict]
```

**功能**:
- 查找起始标题和结束标题
- 提取两者之间的所有content
- 不包含标题本身
- 支持结束标题为None（提取到结尾）

**使用场景**:
```python
# 提取"第一章 概述"到"第二章 系统建设要求"之间的内容
contents = TitleMatcher.find_content_range_by_titles(
    "第一章 概述",
    "第二章 系统建设要求",
    content_list,
    page_range=(1, 5)
)
```

#### 1.5 内容转文本（包含Markdown转换）
```python
TitleMatcher.extract_text_from_contents(
    contents: List[Dict]
) -> str
```

**转换规则**:
- **text**: 直接提取text字段
- **list**: 每个list_item换行拼接
- **image**: 转换为 `![caption](img_path)` 格式
- **table**: 转换为 `![caption](img_path)` 格式
- **无caption**: 使用文件名作为caption

**示例输出**:
```markdown
这是第一段文本

列表项1
列表项2
列表项3

![图1 碳素钢和低合金钢钢板的适用范围](images/xxx.jpg)

这是第二段文本

![表1 测试表格](images/table.jpg)
```

---

### 2. 便捷函数
**文件**: [`app/utils/title_matcher.py`](app/utils/title_matcher.py)

提供两个简化调用的便捷函数：

```python
# 查找标题匹配
idx = find_title_match(title, content_list, page_range)

# 根据标题范围提取文本
text = extract_content_by_title_range(
    start_title,
    end_title,
    content_list,
    page_range
)
```

---

### 3. 完整单元测试
**文件**: [`tests/test_title_matcher.py`](tests/test_title_matcher.py)

**测试覆盖**:
- ✅ 标题归一化（空格、标点、大小写）
- ✅ 标题包含判断（精确、模糊、不匹配）
- ✅ content_list查找（text、list、page_range）
- ✅ 标题范围提取（有/无结束标题）
- ✅ 文本提取（text、list、image、table、混合）
- ✅ 便捷函数

**测试类**:
1. `TestTitleNormalization` - 标题归一化测试
2. `TestTitleContainment` - 标题包含判断测试
3. `TestFindTitleInContentList` - 查找标题测试
4. `TestFindContentRangeByTitles` - 范围提取测试
5. `TestExtractTextFromContents` - 文本提取测试
6. `TestConvenienceFunctions` - 便捷函数测试

**运行测试**:
```bash
pytest tests/test_title_matcher.py -v
```

---

## 🎯 关键设计决策

### 1. 归一化策略
**决策**: 移除空格和标点，保留§等特殊符号
**原因**: 
- 空格和标点格式差异最常见
- §、第、章等是标题的关键标识
- 转小写统一中英文混合标题

### 2. 相似度算法
**决策**: 使用SequenceMatcher，默认阈值0.85
**原因**:
- 算法简单高效
- 对标题轻微差异容忍度好
- 0.85在准确性和容错性间平衡

### 3. 图片/表格处理
**决策**: 转换为Markdown格式，包含caption
**原因**:
- Markdown格式统一，便于后续处理
- caption提供语义信息，方便视觉模型理解
- 文件名作为fallback，确保总有描述

### 4. 标题范围提取
**决策**: 不包含起始和结束标题本身
**原因**:
- 标题已在节点信息中
- 避免重复
- 符合"标题下的内容"语义

---

## 📊 性能分析

### 时间复杂度
- `normalize_title`: O(n) - n为标题长度
- `is_title_contained`: O(n*m) - n、m为两个字符串长度
- `find_title_in_content_list`: O(k*n) - k为content数量，n为平均文本长度
- `find_content_range_by_titles`: O(k) - k为content数量

### 空间复杂度
- 所有函数：O(1) - 仅归一化字符串的临时存储

### 优化建议
- 如果content_list很大（>10000），考虑：
  - 按页面索引建立倒排索引
  - 使用更高效的模糊匹配算法（如Levenshtein距离）

---

## 🔍 测试结果

### 关键测试用例

#### ✅ 空格差异处理
```python
"第二章 系统建设要求" ≈ "第二章系统建设要求"  # True
```

#### ✅ 子标题包含
```python
"§2.1. 基础功能部分" in "§2.1. 基础功能部分§2.1.1. 企业用户"  # True
```

#### ✅ 图片Markdown转换
```python
{
  "type": "image",
  "img_path": "images/test.jpg",
  "image_caption": ["图1", "测试图片"]
}
→ "![图1 测试图片](images/test.jpg)"
```

#### ✅ 表格Markdown转换
```python
{
  "type": "table",
  "img_path": "images/table.jpg",
  "table_caption": ["表1", "测试表格"]
}
→ "![表1 测试表格](images/table.jpg)"
```

#### ✅ 无caption处理
```python
{
  "type": "image",
  "img_path": "images/abc123.jpg",
  "image_caption": []
}
→ "![abc123.jpg](images/abc123.jpg)"
```

---

## 💡 使用示例

### 示例1: 查找标题
```python
from app.utils.title_matcher import find_title_match

# MinerU解析结果
content_list = [
    {"type": "text", "text": "第一章 概述", "page_idx": 1},
    {"type": "text", "text": "内容...", "page_idx": 1},
]

# 查找标题索引
idx = find_title_match("第一章 概述", content_list)
# idx = 0
```

### 示例2: 提取标题间内容
```python
from app.utils.title_matcher import extract_content_by_title_range

text = extract_content_by_title_range(
    start_title="第一章 概述",
    end_title="第二章 系统建设要求",
    content_list=content_list,
    page_range=(1, 5)
)
# text = "第一章的所有内容（不含标题）"
```

### 示例3: 处理图片和表格
```python
from app.utils.title_matcher import TitleMatcher

contents = [
    {"type": "text", "text": "性能要求如下："},
    {
        "type": "image",
        "img_path": "images/perf.jpg",
        "image_caption": ["图1", "性能指标"]
    },
    {"type": "text", "text": "需满足以上要求。"}
]

text = TitleMatcher.extract_text_from_contents(contents)
# 输出:
# 性能要求如下：
#
# ![图1 性能指标](images/perf.jpg)
#
# 需满足以上要求。
```

---

## ✅ 验收标准

### 已满足
- [x] 标题归一化正确处理空格、标点
- [x] 支持模糊匹配（相似度阈值可配置）
- [x] 能在content_list中正确查找标题
- [x] 支持页面范围过滤
- [x] 正确提取标题间的内容
- [x] 图片转换为Markdown格式
- [x] 表格转换为Markdown格式
- [x] 无caption时使用文件名
- [x] 完整的单元测试覆盖
- [x] 所有测试用例通过

---

## 🔄 与其他阶段的关系

### 为阶段3准备
阶段3将使用这些函数改造text_filler：
```python
# text_filler将使用
from app.utils.title_matcher import extract_content_by_title_range

original_text = extract_content_by_title_range(
    start_title=node.title,
    end_title=end_boundary_title,
    content_list=mineru_content_list,
    page_range=(start_page, end_page)
)
```

### 已包含阶段4部分工作
- ✅ 图片/表格Markdown转换已在TitleMatcher中实现
- ✅ caption处理逻辑已完成
- 阶段4可标记为部分完成

---

## 📂 文件结构更新

```
TenderAnalysis/
├── app/
│   ├── utils/                      
│   │   ├── __init__.py             ✅ 新增
│   │   └── title_matcher.py        ✅ 新增（核心算法）
│   ├── services/
│   │   └── mineru_service.py       ✅ 阶段1
│   ├── nodes/
│   │   ├── mineru_parser.py        ✅ 阶段1
│   │   └── text_filler.py          (待改造 - 阶段3)
│   └── core/
│       ├── states.py               ✅ 阶段1
│       └── graph.py                ✅ 阶段1
└── tests/
    └── test_title_matcher.py       ✅ 新增（单元测试）
```

---

## 🔄 下一步：阶段3

**阶段3: 原文填充逻辑改造（基于content_list）**

**目标**:
- 改造 `text_filler.py`
- 使用title_matcher基于content_list填充original_text
- 移除PyPDF2调用
- 支持图片/表格的Markdown格式

**预计改动**:
```python
# 旧逻辑
page_text = extract_pages_text(pdf_path, start_page, end_page)
original_text = extract_original_text_with_llm(node_title, page_text, end_boundary_title)

# 新逻辑
original_text = extract_content_by_title_range(
    start_title=node.title,
    end_title=end_boundary_title,
    content_list=state["mineru_content_list"],
    page_range=(start_page, end_page)
)
```

---

## ⚠️ 已知限制

### 1. 标题匹配准确性
- 依赖相似度阈值（默认0.85）
- 极端情况可能误匹配
- 建议：后续可添加日志，记录匹配置信度

### 2. 性能
- 大文档（>1000页）可能较慢
- 建议：添加缓存机制

### 3. 特殊字符
- 部分特殊符号可能影响匹配
- 建议：扩展normalize_title的处理规则

---

## ✅ 阶段2总结

**成果**:
- ✅ 实现了鲁棒的标题匹配算法
- ✅ 支持图片/表格Markdown转换
- ✅ 完整的单元测试覆盖
- ✅ 便捷的API接口

**质量**:
- 代码规范，注释完整
- 测试覆盖全面
- 性能可接受

**下一步**:
- 需要用户确认是否继续阶段3
- 阶段3将是最大的改动：重构text_filler
- 预计影响：移除LLM调用，提升速度和准确性