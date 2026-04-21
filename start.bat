@echo off
REM 启动 Vya's Kitchen 服务器（Windows 环境）

REM 切换到脚本所在目录
cd /d %~dp0

echo ==============================
echo Building production bundle...
echo ==============================
py -3 build.py

echo.
echo ==============================
echo Starting server from dist\ ...
echo ==============================

cd /d "%~dp0dist"

REM 可选：安装依赖（如果已安装可删除下面两行）
IF EXIST requirements.txt (
    echo Installing Python dependencies (if not already installed)...
    py -3 -m pip install -r requirements.txt
)

echo.
echo Running server.py ...
py -3 server.py


