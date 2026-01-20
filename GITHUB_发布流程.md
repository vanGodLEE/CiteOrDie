# GitHub 手动发布流程

## 📋 前提条件

- ✅ 项目结构已整理（backend/ + frontend/）
- ✅ 敏感数据已清理（无.env，无.db文件）
- ✅ README.md 已更新

---

## 🚀 发布步骤（5分钟）

### 1. 在GitHub创建仓库

访问：https://github.com/new

填写信息：
- **Repository name**: `CiteOrDie`
- **Description**: `智能文档条款提取系统 - 基于LangGraph和MinerU的PDF文档解析与条款提取`
- **Public** ✅
- **不要勾选** "Initialize with README" ❌

点击 "Create repository"

---

### 2. 初始化Git仓库

```powershell
cd D:\dev\CiteOrDie

# 初始化
git init

# 添加所有文件
git add .

# 查看将要提交的文件
git status
```

---

### 3. 创建首次提交

```powershell
git commit -m "feat: initial commit - intelligent document clause extraction system

Features:
- PDF document parsing with MinerU and PageIndex
- 7-dimension clause extraction using LLM
- LangGraph workflow orchestration
- Vue3 frontend with real-time progress tracking
- Multi-LLM provider support (OpenAI, DeepSeek, Qwen)
- Quality report and statistics
- Task history management
- Excel export functionality

Tech Stack:
- Backend: Python 3.10+, FastAPI, LangGraph, MinerU, SQLite
- Frontend: Vue 3, Element Plus, PDF.js
- Infrastructure: MinIO, Docker (optional)
"
```

---

### 4. 连接远程仓库

**替换 YOUR_USERNAME 为你的GitHub用户名：**

```powershell
git remote add origin https://github.com/YOUR_USERNAME/CiteOrDie.git

git branch -M main
```

---

### 5. 推送代码

```powershell
git push -u origin main
```

如果遇到权限问题，需要配置：
- SSH密钥：https://docs.github.com/zh/authentication/connecting-to-github-with-ssh
- 或Personal Access Token：https://docs.github.com/zh/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token

---

### 6. 创建Release（可选）

```powershell
# 创建版本标签
git tag -a v1.0.0 -m "Initial public release"

# 推送标签
git push origin v1.0.0
```

然后访问 GitHub 仓库的 Releases 页面创建正式发布。

---

## ✅ 完成！

你的项目现在已经开源了！

**仓库地址**：`https://github.com/YOUR_USERNAME/CiteOrDie`

---

## 📝 发布后的优化（可选）

1. **更新README**
   - 替换 `YOUR_USERNAME` 为实际用户名
   - 添加项目截图

2. **添加徽章**
   ```markdown
   [![Stars](https://img.shields.io/github/stars/YOUR_USERNAME/CiteOrDie)](https://github.com/YOUR_USERNAME/CiteOrDie/stargazers)
   [![Issues](https://img.shields.io/github/issues/YOUR_USERNAME/CiteOrDie)](https://github.com/YOUR_USERNAME/CiteOrDie/issues)
   ```

3. **完善文档**
   - 添加使用示例
   - 添加FAQ

4. **分享项目**
   - Twitter, LinkedIn, 知乎
   - Reddit, Hacker News
   - 相关技术社区

---

阅读完成后可删除此文件。
