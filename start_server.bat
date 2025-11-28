@echo off
REM 智能招标书分析系统 - 启动脚本

echo ========================================
echo 智能招标书分析系统
echo ========================================
echo.

REM 检查虚拟环境
if not exist "venv\Scripts\activate.bat" (
    echo [错误] 虚拟环境不存在
    echo 请先运行: python -m venv venv
    pause
    exit /b 1
)

REM 激活虚拟环境
echo [1] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 检查.env文件
if not exist ".env" (
    echo.
    echo [警告] .env文件不存在
    echo 请复制配置模板:
    echo   - 使用OpenAI: copy .env.example .env
    echo   - 使用DeepSeek: copy env.deepseek.template .env
    echo.
    pause
    exit /b 1
)

echo [2] 配置检查通过
echo.

REM 检查端口占用
netstat -ano | findstr :8000 >nul
if %errorlevel% equ 0 (
    echo [警告] 端口8000已被占用
    echo 如果是旧服务，请先关闭它
    echo.
)

REM 启动服务
echo [3] 启动FastAPI服务...
echo.
echo 服务将运行在: http://127.0.0.1:8000
echo API文档: http://127.0.0.1:8000/docs
echo.
echo 按 Ctrl+C 停止服务
echo.
echo ========================================
echo.

uvicorn app.api.main:app --reload --port 8000

pause

