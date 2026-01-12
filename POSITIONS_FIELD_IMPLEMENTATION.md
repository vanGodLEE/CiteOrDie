# Positions字段实现文档

## 功能概述

为PageIndexNode添加`positions`字段，用于存储从起始标题（闭区间）到结束标题（开区间）之间所有文本内容的bbox坐标。

## 实现细节

### 1. 数据模型扩展

**文件**: `app/core/states.py`

```python
class PageIndexNode(BaseModel):
    """PageIndex的节点模型"""
    
    # ... 其他字段 ...
    
    # **新增：bbox坐标字段**
    positions: List[List[int]] = Field(
        default_factory=list,
        description="原文内容的bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]"
    )
```

**数据格式说明**：
- `positions`是一个二维列表
- 每个元素是一个长度为5的列表：`[page_idx, x1, y1, x2, y2]`
- `page_idx`: MinerU的页码索引（0-based）
- `x1, y1`: bbox左上角坐标
- `x2, y2`: bbox右下角坐标

### 2. bbox提取函数

**文件**: `app/utils/title_matcher.py`

#### 2.1 基础函数 - `extract_bbox_positions()`

```python
def extract_bbox_positions(contents: List[Dict[str, Any]]) -> List[List[int]]:
    """
    从content列表中提取所有bbox坐标
    
    Returns:
        bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]
    """
```

#### 2.2 核心函数 - `extract_bbox_positions_with_titles()`

```python
def extract_bbox_positions_with_titles(
    start_title: str,
    end_title: Optional[str],
    content_list: List[Dict[str, Any]],
    page_range: Optional[Tuple[int, int]] = None
) -> List[List[int]]:
    """
    根据标题范围提取bbox坐标（闭区间起始标题，开区间结束标题）
    
    Args:
        start_title: 起始标题（闭区间，包含该标题）
        end_title: 结束标题（开区间，不包含该标题）
        content_list: MinerU解析的content列表
        page_range: 页面范围（start_page, end_page）
        
    Returns:
        bbox坐标列表，格式：[[page_idx, x1, y1, x2, y2], ...]
    """
```

**关键逻辑**：
1. 查找起始标题索引（`start_idx`）
2. 查找结束标题索引（`end_idx`）
3. 提取范围：`[start_idx, end_idx)` - **包含起始标题，不包含结束标题**
4. 只提取包含bbox和page_idx的content

### 3. 原文填充逻辑

**文件**: `app/nodes/text_filler.py`

#### 3.1 导入新函数

```python
from app.utils.title_matcher import extract_content_by_title_range, extract_bbox_positions_with_titles
```

#### 3.2 填充positions字段

在`fill_single_node_text()`函数中：

```python
# 提取原文
original_text = extract_content_by_title_range(
    start_title=node.title,
    end_title=end_boundary_title,
    content_list=mineru_content_list,
    page_range=(mineru_start_page, mineru_end_page)
)

# 提取bbox坐标（闭区间起始标题，开区间结束标题）
positions = extract_bbox_positions_with_titles(
    start_title=node.title,
    end_title=end_boundary_title,
    content_list=mineru_content_list,
    page_range=(mineru_start_page, mineru_end_page)
)

# 填充到节点
node.original_text = original_text if original_text else ""
node.positions = positions if positions else []
```

#### 3.3 错误处理

确保在所有错误情况下都初始化positions为空列表：

```python
# 各种异常处理中
node.original_text = ""
node.summary = ""
node.positions = []  # 新增
```

## 使用示例

### 输入示例（MinerU content_list）

```json
[
  {
    "type": "text",
    "text": "1.招标条件",
    "text_level": 1,
    "bbox": [90, 127, 196, 143],
    "page_idx": 6
  },
  {
    "type": "text",
    "text": "本招标项目某项目高性能资源调度系统...",
    "bbox": [89, 155, 887, 227],
    "page_idx": 6
  },
  {
    "type": "text",
    "text": "2.项目概况与招标范围",
    "text_level": 1,
    "bbox": [90, 237, 297, 255],
    "page_idx": 6
  }
]
```

### 输出示例（PageIndexNode.positions）

对于标题"1.招标条件"（结束边界是"2.项目概况与招标范围"）：

```python
node.positions = [
  [6, 90, 127, 196, 143],   # 起始标题（闭区间，包含）
  [6, 89, 155, 887, 227]    # 正文内容
  # 结束标题不包含（开区间）
]
```

## 关键特性

### 1. 闭区间起始，开区间结束

- **起始标题**：包含在positions中（闭区间）
- **结束标题**：不包含在positions中（开区间）
- 符合用户要求："起始标题（闭区间）到结束标题（开区间）"

### 2. 完整的页面范围支持

- 支持PageIndex页码范围（1-based）
- 自动转换为MinerU页码（0-based）
- 支持动态扩展页面范围

### 3. 错误容忍

- 如果找不到起始标题，返回空列表
- 如果找不到结束标题，扩展到页面范围结尾
- 只提取包含有效bbox的content

### 4. 标题bbox保留策略

**重要特性**：即使节点没有正文内容（`original_text`为空），标题本身的bbox坐标也会被保留。

```python
# 即使original_text为空，positions也不会被清空
if original_text and len(original_text.strip()) > 0:
    # 有正文内容
    node.summary = summary
else:
    # 没有正文内容，但保留标题的bbox
    node.summary = ""
    # 不要清空positions！保留标题的bbox
```

**应用场景**：
- 父节点（有子节点）：通常只有标题没有正文，但positions包含标题bbox
- 空章节：只有标题没有内容的章节，positions包含标题bbox
- 匹配失败：标题匹配失败时，positions仍可能包含部分bbox

### 5. 日志输出

```python
# 有正文内容
logger.debug(f"   ✅ 原文提取成功: 长度={len(original_text)}")
logger.debug(f"   📍 坐标提取成功: {len(positions)} 个bbox")

# 无正文内容但保留bbox
logger.debug(
    f"   ℹ️  节点无正文内容: original_text已设为空字符串\n"
    f"   📍 但保留了标题bbox: {len(positions)} 个坐标"
)
```

## 测试验证

### 验证点

1. **数据模型验证**
   - [ ] PageIndexNode包含positions字段
   - [ ] positions格式正确：`List[List[int]]`
   - [ ] 默认值为空列表

2. **功能验证**
   - [ ] 起始标题包含在positions中
   - [ ] 结束标题不包含在positions中
   - [ ] bbox格式正确：`[page_idx, x1, y1, x2, y2]`
   - [ ] page_idx为MinerU的0-based索引

3. **边界情况验证**
   - [ ] 叶子节点的positions
   - [ ] 有子节点的节点的positions（只有标题没有正文）
   - [ ] 文档最后节点的positions
   - [ ] 空节点的positions（original_text为空但positions包含标题bbox）
   - [ ] 找不到标题时的positions（应为空列表）

4. **标题bbox保留验证**
   - [ ] 父节点（有子节点）的positions包含标题bbox
   - [ ] 空章节的positions包含标题bbox
   - [ ] positions不会因为original_text为空而被清空

## 技术细节

### MinerU Content结构

```python
{
  "type": "text",           # content类型
  "text": "...",            # 文本内容
  "bbox": [x1, y1, x2, y2], # bbox坐标
  "page_idx": 6             # 页码索引（0-based）
}
```

### PageIndex vs MinerU 页码对照

- **PageIndex**: 1-based（第1页 = start_index: 1）
- **MinerU**: 0-based（第1页 = page_idx: 0）
- **转换公式**: `mineru_page_idx = pageindex_page - 1`

## 影响范围

### 修改的文件

1. `app/core/states.py` - 添加positions字段
2. `app/utils/title_matcher.py` - 添加bbox提取函数
3. `app/nodes/text_filler.py` - 填充positions字段

### 向后兼容性

- ✅ **完全向后兼容** - positions字段有默认值（空列表）
- ✅ 已有代码不受影响
- ✅ API响应自动包含新字段（Pydantic自动序列化）

## 未来扩展

### 可能的优化

1. **坐标归一化**
   - 将bbox坐标归一化到[0, 1]范围
   - 便于不同分辨率下的显示

2. **坐标压缩**
   - 对于大量bbox，考虑压缩存储
   - 使用增量编码减少存储空间

3. **可视化支持**
   - 前端根据positions在PDF上高亮显示
   - 支持点击positions跳转到PDF对应位置

4. **OCR校验**
   - 使用positions进行OCR准确性校验
   - 对比OCR结果与实际文本位置

## Bug修复记录

### Bug #1: 空节点的positions被清空

**问题描述**：
- 当节点没有正文内容（`original_text`为空）时，`positions`字段也被强制清空
- 导致父节点（有子节点）和空章节的标题bbox丢失

**根本原因**：
```python
# 错误代码（已修复）
else:
    node.summary = ""
    node.positions = []  # ❌ 错误：清空了标题的bbox
```

**修复方案**：
```python
# 修复后代码
else:
    node.summary = ""
    # ✅ 正确：不清空positions，保留标题的bbox
```

**影响范围**：
- 所有父节点（有子节点的节点）
- 所有只有标题没有正文的节点

**修复时间**: 2026-01-09 11:19

---

## 总结

本次实现为PageIndexNode添加了`positions`字段，用于存储原文内容的精确bbox坐标。实现遵循"闭区间起始，开区间结束"的原则，完全向后兼容，并提供了完整的错误处理和日志输出。

**关键特性**：
1. ✅ 闭区间起始标题，开区间结束标题
2. ✅ 即使没有正文内容，也保留标题bbox
3. ✅ 完整的页面范围支持和索引转换
4. ✅ 完全向后兼容

---

**实现日期**: 2026-01-09
**修复日期**: 2026-01-09
**实现者**: Kilo Code
**版本**: v1.1