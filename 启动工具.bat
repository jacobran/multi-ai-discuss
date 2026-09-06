@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   多 AI 议事助手 - 本地代理启动中
echo ================================================
echo.
echo 启动后会自动打开浏览器，地址: http://localhost:8787
echo 注意：不要直接双击 index.html，必须通过本脚本启动
echo 关闭此黑色窗口即停止服务
echo.
python server.py
pause
