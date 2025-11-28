# Git版本管理指南

## 📋 当前版本

```
v1.0 - 智能招标书分析系统
Commit: 8657237
Branch: master
```

---

## 🌿 分支策略

### 主分支
- `master` - 稳定的生产版本

### 功能分支 (推荐)
```bash
# 创建新功能分支
git checkout -b feature/需求导出Excel功能
git checkout -b feature/前端界面优化

# 创建修复分支
git checkout -b fix/修复并发bug
git checkout -b fix/修复LLM超时

# 创建重构分支
git checkout -b refactor/优化数据库查询
```

---

## 📝 提交规范

### Commit Message 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档修改
- `style`: 代码格式（不影响功能）
- `refactor`: 重构代码
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具链修改

### 示例

```bash
# 新功能
git commit -m "feat(api): 添加Excel导出接口

- 支持导出需求矩阵到Excel
- 支持自定义模板
- 支持批量导出

Closes #123"

# 修复bug
git commit -m "fix(database): 修复SQLite并发冲突

- 使用NullPool替代StaticPool
- 移除跨线程的refresh操作
- 添加超时处理

Fixes #456"

# 文档更新
git commit -m "docs: 更新数据库设计文档"

# 性能优化
git commit -m "perf(extractor): 优化需求提取性能

- 使用批量查询减少数据库访问
- 优化LLM调用逻辑"
```

---

## 🔄 常用操作

### 1. 日常开发流程

```bash
# 1. 更新代码
git pull origin master

# 2. 创建功能分支
git checkout -b feature/新功能

# 3. 开发并提交
git add .
git commit -m "feat: 添加新功能"

# 4. 推送到远程（如果有）
git push origin feature/新功能

# 5. 合并到主分支
git checkout master
git merge feature/新功能

# 6. 删除功能分支
git branch -d feature/新功能
```

### 2. 查看历史

```bash
# 查看提交历史
git log --oneline

# 查看详细历史
git log --graph --oneline --all

# 查看某个文件的修改历史
git log --follow app/core/graph.py

# 查看某次提交的详细信息
git show 8657237
```

### 3. 撤销修改

```bash
# 撤销工作区修改
git checkout -- app/core/graph.py

# 撤销暂存区修改
git reset HEAD app/core/graph.py

# 撤销最后一次提交（保留修改）
git reset --soft HEAD^

# 撤销最后一次提交（丢弃修改）
git reset --hard HEAD^
```

### 4. 查看差异

```bash
# 查看工作区修改
git diff

# 查看暂存区修改
git diff --cached

# 比较两个提交
git diff 8657237 HEAD

# 查看文件历史
git log -p app/core/graph.py
```

---

## 📦 版本标签

### 创建版本标签

```bash
# 创建轻量标签
git tag v1.0

# 创建附注标签（推荐）
git tag -a v1.1 -m "版本 1.1
- 添加Excel导出功能
- 修复并发bug
- 优化性能"

# 查看所有标签
git tag

# 查看标签详情
git show v1.0

# 推送标签到远程
git push origin v1.0
git push origin --tags  # 推送所有标签
```

### 版本规范

遵循语义化版本（SemVer）：`MAJOR.MINOR.PATCH`

- `MAJOR`: 重大变更（不兼容的API修改）
- `MINOR`: 新功能（向后兼容）
- `PATCH`: Bug修复（向后兼容）

**示例**：
- `v1.0.0` - 初始版本
- `v1.1.0` - 添加Excel导出功能
- `v1.1.1` - 修复导出bug
- `v2.0.0` - 重构数据库架构（破坏性变更）

---

## 🚫 .gitignore 说明

已忽略的文件/目录：

```
__pycache__/          # Python缓存
venv/                 # 虚拟环境
.env                  # 敏感配置
temp/mineru_output/   # MinerU临时文件
data/*.db             # 数据库文件
*.log                 # 日志文件
```

### 强制添加已忽略的文件

```bash
git add -f data/important.db  # 强制添加
```

---

## 🔗 远程仓库操作

### 添加远程仓库

```bash
# GitHub
git remote add origin https://github.com/username/TenderAnalysis.git

# GitLab
git remote add origin https://gitlab.com/username/TenderAnalysis.git

# Gitee
git remote add origin https://gitee.com/username/TenderAnalysis.git
```

### 推送代码

```bash
# 首次推送
git push -u origin master

# 后续推送
git push

# 推送所有分支
git push --all

# 推送标签
git push --tags
```

### 克隆仓库

```bash
# 克隆仓库
git clone https://github.com/username/TenderAnalysis.git

# 克隆特定分支
git clone -b develop https://github.com/username/TenderAnalysis.git
```

---

## 📊 查看状态

```bash
# 查看当前状态
git status

# 查看简洁状态
git status -s

# 查看分支
git branch -a

# 查看远程仓库
git remote -v
```

---

## 🛠️ 高级操作

### 1. 储藏修改

```bash
# 储藏当前修改
git stash

# 查看储藏列表
git stash list

# 恢复最近的储藏
git stash pop

# 恢复特定储藏
git stash apply stash@{0}

# 删除储藏
git stash drop stash@{0}
```

### 2. 交互式暂存

```bash
# 交互式添加文件的部分修改
git add -p app/core/graph.py
```

### 3. 修改历史

```bash
# 修改最后一次提交消息
git commit --amend

# 交互式变基（修改历史）
git rebase -i HEAD~3
```

---

## 🎯 最佳实践

### ✅ 推荐做法

1. **频繁提交**：小步快跑，每个功能点提交一次
2. **有意义的提交消息**：清晰描述改动内容
3. **分支开发**：不直接在master上开发
4. **代码审查**：合并前进行code review
5. **标签管理**：重要版本打标签

### ❌ 避免做法

1. 不要提交敏感信息（.env文件）
2. 不要提交编译产物（__pycache__）
3. 不要提交临时文件（.log, .tmp）
4. 不要提交大文件（PDF、数据库备份）
5. 不要直接push --force到主分支

---

## 📚 参考资源

- [Git官方文档](https://git-scm.com/doc)
- [语义化版本规范](https://semver.org/lang/zh-CN/)
- [约定式提交规范](https://www.conventionalcommits.org/zh-hans/)

---

## 🎉 快速命令速查

```bash
# 初始化
git init

# 克隆
git clone <url>

# 状态
git status

# 添加
git add .

# 提交
git commit -m "message"

# 推送
git push

# 拉取
git pull

# 分支
git checkout -b feature/xxx

# 合并
git merge feature/xxx

# 标签
git tag -a v1.0 -m "版本1.0"

# 日志
git log --oneline

# 差异
git diff
```

