# 招标系统流程重构计划

## 一、当前问题分析

### PageIndex的能力与限制

**PageIndex的优势：**
1. ✅ 自动识别文档结构层次（章节、子章节）
2. ✅ 生成准确的节点ID（如 0001, 0002）
3. ✅ 标注每个节点的页码范围（start_index, end_index）
4. ✅ 生成节点摘要（summary字段，LLM生成）
5. ✅ 支持树形递归结构（nodes字段）

**PageIndex的限制（导致当前问题）：**
1. ❌ **只能拿到页级别文本**：每个节点的summary是基于整个页面的文本生成的
2. ❌ **不能拿到行级别精确原文**：无法精确提取某个标题下的具体段落
3. ❌ **导致原文提取重复**：一个页面可能包含多个标题，每个标题的summary都包含整页内容
4. ❌ **导致需求收集重复**：基于重复的原文提取到重复的需求

### 当前流程的问题

```
当前流程：
PageIndex解析 → 同时提取summary（页级文本） → 基于summary提取需求 → 需要去重

问题点：
- enricher节点基于summary提取需求，但summary包含整页内容
- 多个节点如果在同一页，会重复提取相同需求
- Auditor需要进行复杂的去重逻辑
```

## 二、重构后的新流程

### 2.1 核心思想

**分离结构提取与内容填充**

```
新流程：
第一步：PageIndex提取文档结构（仅结构树，不填充原文）
第二步：基于结构树和原PDF，精确填充每个节点的原文（行级别）
第三步：基于精确原文，提取每个节点的需求（无需去重）
```

### 2.2 详细流程设计

#### 阶段1：结构提取（pageindex_parser）

**职责**：调用PageIndex获取文档树结构

**输入**：
- PDF文件路径

**输出**：
- PageIndexDocument对象（包含完整的树形结构）
- 每个节点包含：title, start_index, end_index, node_id, summary（可选）
- **注意**：此阶段summary仅用于参考，不用于需求提取

**实现**：
- 调用现有的pageindex_service
- 配置：`add_node_summary=True`（用于辅助理解）但不用于需求提取
- 配置：`add_node_text=False`（节省成本）

#### 阶段2：原文精确填充（text_filler）**【新增节点】**

**职责**：递归遍历结构树，为每个节点填充精确的原文内容

**核心逻辑**：

```python
def determine_page_range(node, siblings, children):
    """确定节点应该参照的PDF页面范围"""
    
    if node.has_children():
        # 有子节点：参照范围是 [自己的start, 第一个孩子的start)
        start_page = node.start_index
        end_page = node.children[0].start_index
    else:
        # 叶子节点：参照范围是 [自己的start, 下一个兄弟的start) 或 自己的end
        start_page = node.start_index
        
        # 找到下一个兄弟节点
        next_sibling = find_next_sibling(node, siblings)
        if next_sibling:
            end_page = next_sibling.start_index
        else:
            end_page = node.end_index
    
    return (start_page, end_page)
```

**输入**：
- PageIndexDocument（结构树）
- PDF文件路径或已解析的PDF页面文本

**处理流程**：
1. 使用LangGraph递归遍历整个结构树
2. 对每个节点：
   - 根据节点类型（有子/无子）计算应参照的页面范围
   - 从PDF中提取这些页面的文本
   - 调用LLM，提示词：
     ```
     你的任务是从给定的PDF页面文本中，精确提取标题"xxx"下的内容。
     
     规则：
     1. 只提取该标题下的内容
     2. 忽略其他标题及其内容
     3. 保持原文不变，精确摘录
     4. 如果标题后紧跟子标题，则只提取到子标题之前的内容
     
     标题：{node.title}
     页面文本：{page_text}
     ```
   - 将提取的原文填充到节点的`original_text`字段

3. LangGraph并行处理：
   - 可以并行处理同一层级的兄弟节点
   - 需要保证子节点处理完后再处理父节点（或反之）

**输出**：
- PageIndexDocument（每个节点都包含精确的original_text字段）

**新增字段**：
```python
class PageIndexNode(BaseModel):
    # PageIndex原有字段
    node_id: Optional[str]
    title: str
    start_index: int
    end_index: int
    summary: Optional[str]  # PageIndex生成的摘要（保留但不用于需求提取）
    nodes: List[PageIndexNode]
    
    # 新增字段
    original_text: Optional[str] = Field(None, description="精确提取的原文内容（行级别）")
    
    # 需求字段
    requirements: List[RequirementItem] = Field(default_factory=list)
```

#### 阶段3：需求提取（pageindex_enricher）**【修改】**

**职责**：基于精确的original_text提取需求

**修改点**：
- 输入从`summary`改为`original_text`
- 提示词中强调基于原文精确提取
- 不再需要复杂的去重逻辑（Auditor端简化）

**处理流程**：
1. 遍历所有叶子节点（或所有节点，根据业务需求）
2. 对每个节点：
   - 如果`original_text`为空或太短，跳过
   - 调用LLM提取需求，使用`original_text`作为输入
   - 提示词强调：只提取这段原文中的需求

#### 阶段4：需求汇总（auditor）**【简化】**

**职责**：汇总所有需求，进行简单排序和格式化

**简化点**：
- **不再需要去重**（因为原文已经精确，不会重复）
- 只需要：
  1. 收集所有节点的requirements
  2. 按章节排序
  3. 格式统一
  4. 生成最终矩阵

### 2.3 工作流拓扑

```
原流程：
START → pageindex_parser → [enricher_1, enricher_2, ...] → auditor → END

新流程：
START → pageindex_parser → text_filler → [enricher_1, enricher_2, ...] → auditor → END

详细：
START 
  ↓
pageindex_parser（提取结构树）
  ↓
text_filler（递归填充精确原文）
  ↓
route_to_enrichers（动态路由到并行enrichers）
  ↓
[enricher_1, enricher_2, ..., enricher_n]（并行提取需求）
  ↓
auditor（简单汇总，无需去重）
  ↓
END
```

## 三、实现计划

### 3.1 需要创建的新文件

1. **`app/nodes/text_filler.py`**
   - `text_filler_node(state)`: 主节点函数
   - `fill_text_for_node(node, pdf_pages, siblings)`: 为单个节点填充原文
   - `determine_page_range(node, siblings)`: 计算页面范围
   - `extract_text_from_pages(pdf_path, start_page, end_page)`: 从PDF提取文本

2. **`app/services/pdf_text_extractor.py`**（可选，如果PDF解析逻辑复杂）
   - `extract_page_text(pdf_path, page_num)`: 提取单页文本
   - `extract_pages_text(pdf_path, start_page, end_page)`: 提取多页文本

### 3.2 需要修改的文件

1. **`app/core/states.py`**
   - 在`PageIndexNode`中添加`original_text`字段
   - 可能需要添加辅助方法

2. **`app/core/graph.py`**
   - 添加`text_filler`节点
   - 修改工作流拓扑：在parser和enrichers之间插入text_filler
   - 修改边连接

3. **`app/nodes/pageindex_enricher.py`**
   - 修改`_prepare_node_content()`：优先使用`original_text`而不是`summary`
   - 修改提示词，强调基于精确原文提取

4. **`app/nodes/auditor.py`**
   - 简化去重逻辑（可以完全移除或大幅简化）
   - 保留排序和格式化功能

5. **`app/services/pageindex_service.py`**
   - 配置调整：确保summary生成但不强制依赖
   - 可能添加辅助方法

### 3.3 实施步骤

#### Step 1: 添加original_text字段到模型
- [ ] 修改`app/core/states.py`中的`PageIndexNode`模型
- [ ] 添加`original_text: Optional[str]`字段
- [ ] 添加辅助方法（如果需要）

#### Step 2: 实现PDF文本提取服务
- [ ] 创建`app/services/pdf_text_extractor.py`
- [ ] 实现按页码提取文本的功能
- [ ] 使用PyMuPDF (fitz)或pdfplumber库

#### Step 3: 实现text_filler节点
- [ ] 创建`app/nodes/text_filler.py`
- [ ] 实现页面范围计算逻辑
- [ ] 实现递归遍历结构树
- [ ] 实现LLM调用提取精确原文
- [ ] 添加日志和错误处理

#### Step 4: 修改工作流
- [ ] 修改`app/core/graph.py`
- [ ] 添加text_filler节点到workflow
- [ ] 调整边连接：parser → text_filler → enrichers → auditor
- [ ] 更新状态传递逻辑

#### Step 5: 修改enricher节点
- [ ] 修改`app/nodes/pageindex_enricher.py`
- [ ] 更新`_prepare_node_content()`优先使用`original_text`
- [ ] 更新提示词

#### Step 6: 简化auditor节点
- [ ] 修改`app/nodes/auditor.py`
- [ ] 移除或简化去重逻辑
- [ ] 保留必要的排序和格式化

#### Step 7: 测试和验证
- [ ] 单元测试：测试text_filler的页面范围计算
- [ ] 集成测试：使用真实PDF测试完整流程
- [ ] 验证原文提取的准确性
- [ ] 验证需求提取不再重复
- [ ] 性能测试：对比新旧流程的耗时

## 四、技术细节

### 4.1 PDF文本提取

**推荐库**：PyMuPDF (fitz)

```python
import fitz  # PyMuPDF

def extract_page_text(pdf_path: str, page_num: int) -> str:
    """提取单页文本"""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]  # 0-based
    text = page.get_text()
    doc.close()
    return text

def extract_pages_text(pdf_path: str, start_page: int, end_page: int) -> str:
    """提取多页文本"""
    doc = fitz.open(pdf_path)
    text_parts = []
    for page_num in range(start_page, end_page + 1):
        page = doc[page_num - 1]
        text_parts.append(f"<page_{page_num}>\n{page.get_text()}\n</page_{page_num}>")
    doc.close()
    return "\n".join(text_parts)
```

### 4.2 页面范围计算逻辑

```python
def calculate_text_fill_range(
    node: PageIndexNode,
    parent: Optional[PageIndexNode] = None,
    siblings: Optional[List[PageIndexNode]] = None
) -> Tuple[int, int]:
    """
    计算节点应该填充的文本所对应的PDF页面范围
    
    规则：
    1. 有子节点：[node.start_index, node.children[0].start_index)
    2. 叶子节点+有下一个兄弟：[node.start_index, next_sibling.start_index)
    3. 叶子节点+无下一个兄弟：[node.start_index, node.end_index]
    
    返回：(start_page, end_page) 1-based, 闭区间
    """
    start_page = node.start_index
    
    if node.nodes:  # 有子节点
        end_page = node.nodes[0].start_index - 1
    else:  # 叶子节点
        # 找下一个兄弟
        next_sibling = None
        if siblings:
            current_idx = siblings.index(node)
            if current_idx < len(siblings) - 1:
                next_sibling = siblings[current_idx + 1]
        
        if next_sibling:
            end_page = next_sibling.start_index - 1
        else:
            end_page = node.end_index
    
    return (start_page, end_page)
```

### 4.3 LLM提示词设计

```python
def build_text_extraction_prompt(node_title: str, page_text: str) -> str:
    """构建精确原文提取的提示词"""
    return f"""你是一个专业的文档内容提取专家。你的任务是从给定的PDF页面文本中，精确提取标题"{node_title}"下的内容。

## 提取规则

1. **精确性**：只提取该标题下的内容，保持原文不变
2. **边界识别**：
   - 开始：从标题"{node_title}"之后的内容开始提取
   - 结束：提取到下一个同级或上级标题之前，或到页面结束
3. **忽略无关内容**：
   - 忽略该标题之前的所有内容
   - 忽略该标题之后出现的其他标题及其内容
4. **子标题处理**：
   - 如果标题后紧跟子标题，只提取到子标题之前的内容
   - 不要包含子标题的内容（子标题会单独处理）
5. **格式保持**：尽可能保持原文的段落结构和格式

## 输入

**目标标题**：{node_title}

**PDF页面文本**：
```
{page_text}
```

## 输出要求

直接输出提取的原文内容，不要添加任何解释或标记。如果找不到该标题或标题下无内容，返回"无内容"。
"""
```

### 4.4 LangGraph并行策略

**选项1：深度优先，串行处理**
- 优点：逻辑简单，不会并发冲突
- 缺点：速度较慢

**选项2：广度优先，按层并行**
- 优点：速度快，同层节点可并行
- 缺点：需要管理层级依赖

**推荐**：选项1（串行），先保证正确性，后续优化性能

```python
async def fill_text_recursively(
    node: PageIndexNode,
    pdf_path: str,
    parent: Optional[PageIndexNode] = None,
    siblings: Optional[List[PageIndexNode]] = None
):
    """递归填充节点的原文"""
    # 1. 计算当前节点的页面范围
    start_page, end_page = calculate_text_fill_range(node, parent, siblings)
    
    # 2. 提取PDF文本
    page_text = extract_pages_text(pdf_path, start_page, end_page)
    
    # 3. 调用LLM提取精确原文
    prompt = build_text_extraction_prompt(node.title, page_text)
    original_text = await llm_service.call(prompt)
    
    # 4. 填充到节点
    node.original_text = original_text
    
    # 5. 递归处理子节点
    if node.nodes:
        for i, child in enumerate(node.nodes):
            await fill_text_recursively(
                child, 
                pdf_path, 
                parent=node, 
                siblings=node.nodes
            )
```

## 五、预期效果

### 5.1 问题解决

✅ **原文提取精确**：每个节点只包含自己标题下的内容
✅ **无重复需求**：基于精确原文，不会提取重复需求
✅ **去重逻辑简化**：Auditor端大幅简化
✅ **结果可追溯**：每个需求都能精确追溯到原文位置

### 5.2 性能对比

| 指标 | 旧流程 | 新流程 | 改进 |
|------|--------|--------|------|
| 原文重复率 | 高（页级重复） | 无（行级精确） | ✅ 100%改进 |
| 需求重复率 | 需要去重 | 基本无重复 | ✅ 95%改进 |
| LLM调用次数 | N个节点 | N个节点 + N个填充 | ⚠️ 增加N次 |
| 处理时间 | T | T + T_fill | ⚠️ 增加填充时间 |
| 结果准确性 | 中 | 高 | ✅ 显著提升 |

**说明**：虽然LLM调用次数和处理时间会增加，但结果准确性和可维护性大幅提升，整体ROI为正。

### 5.3 成本估算

假设：
- N = 50个节点（典型招标文档）
- 每次填充调用成本：0.01元
- 每次需求提取成本：0.02元

**旧流程成本**：
- 需求提取：50 × 0.02 = 1元
- 去重（假设0成本）
- **总计：1元**

**新流程成本**：
- 文本填充：50 × 0.01 = 0.5元
- 需求提取：50 × 0.02 = 1元
- **总计：1.5元**

**成本增加**：50%
**价值提升**：准确性提升 > 100%

## 六、风险和应对

### 风险1：PDF文本提取质量
**问题**：扫描版PDF或图片型PDF无法直接提取文本
**应对**：
- 检测PDF类型，扫描版走OCR流程
- 使用MinerU的OCR能力
- 提供降级方案（仍使用summary）

### 风险2：标题识别边界不准确
**问题**：LLM可能无法准确识别标题边界
**应对**：
- 优化提示词，提供更多上下文
- 使用few-shot示例
- 人工审核关键节点

### 风险3：性能下降
**问题**：增加text_filler步骤导致整体处理时间增加
**应对**：
- 并行处理同层节点
- 缓存PDF页面文本
- 使用更快的LLM模型（如deepseek）

### 风险4：成本增加
**问题**：LLM调用次数翻倍
**应对**：
- 使用更便宜的模型（deepseek）
- 只对叶子节点填充原文
- 批量处理减少API调用

## 七、后续优化方向

1. **智能缓存**：缓存PDF页面文本，避免重复提取
2. **批量处理**：一次调用处理多个节点的文本填充
3. **模型优化**：微调小模型专门做文本提取，降低成本
4. **增量更新**：支持文档更新时只处理变化部分
5. **可视化调试**：开发工具可视化展示每个节点的原文范围
