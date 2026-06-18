@echo off
chcp 65001 >nul
echo ========================================
echo   AIBox v5 - 打包為獨立 exe (無黑框)
echo ========================================
echo.
echo [1/2] 安裝必要的套件...
pip install pyinstaller markdown
if %errorlevel% neq 0 (
    echo 套件安裝失敗，請檢查 pip 或網路連線。
    pause
    exit /b 1
)
echo.
echo [2/2] 開始打包 hub.py (隱藏主控台視窗)...
python -m PyInstaller --onefile --noconsole hub.py
if %errorlevel% neq 0 (
    echo 打包失敗，請檢查錯誤訊息。
    pause
    exit /b 1
)
echo.
echo ========================================
echo   打包完成！
echo   執行檔位置：dist\hub.exe (僅 GUI，無黑框)
echo ========================================
pause
