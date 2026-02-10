# 条款数据结构说明

本文档详细说明了 CiteOrDie 系统输出的条款（Clause）数据结构及其各字段的含义。

## 完整数据结构示例

```json
{
    "matrix_id": "0013-CLS-002",
    "node_id": "0013",
    "section_title": "Proposal Submission",
    "type": "obligation",
    "actor": "supplier",
    "action": "submit",
    "object": "Technical Proposal",
    "condition": "if technical requirements are requested",
    "deadline": "before the submission deadline",
    "metric": "completeness of technical documentation",
    "original_text": "(b) Technical Proposal: hqsact.techproposal@nato.int",
    "page_number": 5,
    "positions": [
        [
            4,
            93.636,
            534.6,
            380.664,
            548.856
        ]
    ],
    "img_path": "images/page_5_img_001.jpg",
    "table_caption": "Technical Requirements Submission Table",
    "vision_caption": "Table showing technical proposal submission requirements"
}
```

## 核心字段说明

### 唯一标识字段

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `matrix_id` | `string` | ✅ | 条款的全局唯一标识符，格式为 `{node_id}-CLS-{序号}`，如 `"0013-CLS-002"` 表示节点 0013 下的第 2 个条款 |
| `node_id` | `string` | ✅ | 条款所属章节/节点的 ID，与文档树结构中的节点 ID 对应，如 `"0013"` |

### 结构化字段

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `section_title` | `string` | ✅ | 条款所属章节的标题，如 `"Proposal Submission"` |

### 语义分析字段

这些字段由 LLM 通过语义分析自动提取，用于结构化表达条款的关键要素。

| 字段名 | 类型 | 必填 | 说明 | 可选值 |
|--------|------|------|------|--------|
| `type` | `string` | ✅ | 条款类型，标识条款的性质 | `obligation`（义务）/ `prohibition`（禁止）/ `permission`（许可）/ `condition`（条件）/ `definition`（定义）/ `other`（其他）|
| `actor` | `string` | ✅ | 执行主体，标识谁需要履行该条款 | `supplier`（供应商）/ `buyer`（采购方）/ `both`（双方）/ `other`（其他）|
| `action` | `string` | ❌ | 动作，标识要执行的具体行为 | 动词或短语，如 `"submit"`、`"provide"`、`"must not exceed"` 等 |
| `object` | `string` | ❌ | 对象，标识动作的作用对象 | 名词或名词短语，如 `"Technical Proposal"`、`"delivery date"` 等 |
| `condition` | `string` | ❌ | 触发条件，标识条款生效的前提条件 | 条件短语，如 `"if technical requirements are requested"` |
| `deadline` | `string` | ❌ | 截止时间，标识条款规定的时间要求 | 时间表达式，如 `"within 30 days"`、`"before submission deadline"` |
| `metric` | `string` | ❌ | 评估指标，标识条款的衡量标准或质量要求 | 描述性短语，如 `"completeness of documentation"`、`"95% accuracy"` |

### 原文定位字段

这些字段用于在 PDF 原文中精确定位条款。

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `original_text` | `string` | ✅ | 条款的原始文本，从 PDF 中直接提取 |
| `page_number` | `integer` | ✅ | 条款所在的页码（1-based，即第一页为 1） |
| `positions` | `array` | ✅ | 条款在 PDF 中的边界框（bounding box）坐标数组，每个元素是一个长度为 5 的数组：`[page, x1, y1, x2, y2]`，其中 `page` 是页码（0-based，用于前端渲染），`x1, y1` 是左上角坐标，`x2, y2` 是右下角坐标（单位：点，72 dpi） |

#### `positions` 字段详解

`positions` 是一个二维数组，支持跨页或多段文本的条款定位：

```json
"positions": [
    [4, 93.636, 534.6, 380.664, 548.856],   // 第 5 页的一个文本框
    [4, 93.636, 550.0, 380.664, 564.2],     // 第 5 页的另一个文本框（同一条款可能跨行）
    [5, 93.636, 72.0, 380.664, 86.2]        // 第 6 页的延续部分（跨页条款）
]
```

- **第 1 个元素**（`page`）：页码，从 0 开始计数（第 1 页为 0，第 2 页为 1，以此类推），用于前端 PDF.js 渲染
- **第 2 个元素**（`x1`）：左上角 X 坐标（从页面左边缘开始，单位：点）
- **第 3 个元素**（`y1`）：左上角 Y 坐标（从页面底部开始，单位：点）
- **第 4 个元素**（`x2`）：右下角 X 坐标
- **第 5 个元素**（`y2`）：右下角 Y 坐标

> **注意**：坐标系统使用 PDF 标准坐标系（原点在左下角），前端会自动转换为屏幕坐标系（原点在左上角）。

### 多模态字段（可选）

当条款来源于图片、表格等非纯文本内容时，会包含以下字段：

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `img_path` | `string` | ❌ | 条款来源的图片路径，相对于 MinerU 输出目录，如 `"images/page_5_img_001.jpg"` |
| `table_caption` | `string` | ❌ | 条款来源的表格标题或描述，由 LLM 生成 |
| `vision_caption` | `string` | ❌ | 由视觉模型（Vision LLM）生成的图片内容描述，用于辅助理解图片或表格内容 |

## 数据流转说明

### 1. 条款提取阶段

- **PageIndex 解析**：通过 PageIndex 服务解析 PDF 文档结构，生成文档树（Document Tree）
- **MinerU 解析**：通过 MinerU 服务提取 PDF 的深层内容（文本、表格、图片）及其精确坐标
- **LLM 语义分析**：将章节内容（文本/表格/图片）发送给 LLM，提取结构化条款

### 2. 坐标转换阶段

- MinerU 输出的原始坐标（归一化坐标或 MinerU 特定格式）会被转换为 PDF.js 兼容的绝对坐标
- 转换逻辑位于 `backend/app/utils/mineru_coordinate_converter.py`

### 3. 前端渲染阶段

- 前端通过 `positions` 字段在 PDF 画布上绘制高亮框
- 点击章节标题或条款时，自动滚动并高亮对应位置

## 典型使用场景

### 场景 1：纯文本条款

```json
{
    "matrix_id": "0008-CLS-001",
    "node_id": "0008",
    "section_title": "Delivery Terms",
    "type": "obligation",
    "actor": "supplier",
    "action": "deliver",
    "object": "goods",
    "deadline": "within 30 days",
    "original_text": "The supplier shall deliver all goods within 30 days of order confirmation.",
    "page_number": 3,
    "positions": [[2, 72.0, 600.0, 520.0, 614.0]]
}
```

### 场景 2：来自表格的条款

```json
{
    "matrix_id": "0015-CLS-003",
    "node_id": "0015",
    "section_title": "Technical Specifications",
    "type": "condition",
    "actor": "supplier",
    "object": "CPU performance",
    "metric": "minimum 2.5 GHz",
    "original_text": "CPU: Intel Core i5 or equivalent, minimum 2.5 GHz",
    "page_number": 8,
    "positions": [[7, 100.0, 450.0, 300.0, 520.0]],
    "img_path": "images/page_8_table_001.jpg",
    "table_caption": "Hardware Requirements Table",
    "vision_caption": "Table listing minimum hardware specifications including CPU, RAM, and storage requirements"
}
```

### 场景 3：来自图片的条款

```json
{
    "matrix_id": "0020-CLS-005",
    "node_id": "0020",
    "section_title": "Quality Standards",
    "type": "obligation",
    "actor": "supplier",
    "metric": "ISO 9001 certified",
    "original_text": "All products must meet ISO 9001 quality standards as shown in the certification diagram.",
    "page_number": 12,
    "positions": [[11, 150.0, 300.0, 450.0, 500.0]],
    "img_path": "images/page_12_img_002.jpg",
    "vision_caption": "Diagram showing ISO 9001 quality certification process flow"
}
```

## 数据验证规则

### 必填字段验证

- `matrix_id`、`node_id`、`section_title`、`type`、`actor`、`original_text`、`page_number`、`positions` 必须非空
- `type` 和 `actor` 必须是预定义枚举值之一

### 坐标验证

- `positions` 至少包含一个坐标数组
- 每个坐标数组必须有 5 个元素
- 页码必须在 PDF 页数范围内
- 坐标值必须为非负数

### 语义一致性

- 如果 `type` 为 `obligation`（义务），则 `action` 和 `object` 通常应该非空
- 如果 `img_path` 非空，则应存在对应的图片文件

## 扩展性说明

系统设计支持未来扩展更多字段，例如：

- `priority`：条款优先级（高/中/低）
- `category`：条款分类（技术/商务/法律等）
- `linked_clauses`：关联条款的 `matrix_id` 列表
- `compliance_status`：合规状态（待审核/已通过/不合规）

## 相关文档

- [README.md](../README.md) - 项目主文档
- [架构设计](../README.md#架构与工作流) - 了解条款提取的完整工作流
- [模型推荐](../README.md#模型推荐) - 选择合适的 LLM 以提升提取质量

---

**版本**: 1.0  
**更新日期**: 2026-01-21  
**维护者**: CiteOrDie Team
