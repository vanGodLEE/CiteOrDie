# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-20

### Added
- 🎉 Initial release
- 📄 PDF document parsing using MinerU
- 🤖 Intelligent clause extraction with LLM
- 📊 7-dimension clause structure (type, actor, action, object, condition, deadline, metric)
- 🎯 Precise clause positioning in original PDF
- 📈 Quality report with 4 metrics
- 🔄 Task history and management
- 💾 Data persistence with MinIO
- 🐳 Docker deployment support
- 🌐 Vue3 frontend with PDF viewer
- ⚡ Parallel processing with LangGraph
- 🔌 Multi-LLM provider support (OpenAI, DeepSeek, Qwen)

### Features
- **Backend**:
  - FastAPI REST API
  - LangGraph workflow orchestration
  - MinerU + PageIndex dual-parser
  - SQLite database for task persistence
  - MinIO object storage integration
  - SSE (Server-Sent Events) for real-time progress
  - Excel export functionality
  - Task idempotency with file hash
  - Comprehensive logging

- **Frontend**:
  - Vue 3 + Element Plus UI
  - PDF.js viewer with highlighting
  - Document structure tree view
  - Clause list with filtering
  - Real-time progress tracking
  - Task history management
  - Quality report visualization

- **Deployment**:
  - Docker Compose one-click deployment
  - Nginx reverse proxy configuration
  - Automated deployment scripts
  - Data volume persistence
  - Health checks and auto-restart

### Documentation
- Comprehensive README with quick start guide
- Detailed DEPLOYMENT.md for production setup
- CONTRIBUTING.md for developers
- API documentation with Swagger/OpenAPI
- Configuration examples for different LLM providers

## [Unreleased]

### Planned
- [ ] Support for more document formats (Word, Excel)
- [ ] Multi-language support (i18n)
- [ ] Advanced search and filtering
- [ ] Batch processing
- [ ] API rate limiting
- [ ] User authentication and authorization
- [ ] Performance optimizations
- [ ] More LLM providers
- [ ] Cloud deployment templates (AWS, Azure, GCP)

### Under Consideration
- [ ] Browser extension for quick analysis
- [ ] Mobile app
- [ ] Integration with document management systems
- [ ] Custom clause templates
- [ ] Clause validation rules
- [ ] Collaborative features

---

## Version History

### Version Numbering

- **Major**: Breaking changes, significant feature additions
- **Minor**: New features, backward compatible
- **Patch**: Bug fixes, minor improvements

### Upgrade Guide

When upgrading between major versions, please refer to the migration guides in the `docs/migrations/` directory.

---

For questions about releases, please see our [GitHub Releases](https://github.com/YOUR_USERNAME/CiteOrDie/releases) page.
