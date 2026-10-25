@echo off
rem 从源码启动，不留命令行窗口（需要 Python 3.10 或更新版本）。
rem 启动错误由 app.py 弹窗显示。
where pyw.exe >nul 2>nul && (start "" pyw.exe -3 "%~dp0app.py" & exit /b 0)
where pythonw.exe >nul 2>nul && (start "" pythonw.exe "%~dp0app.py" & exit /b 0)
echo Python 3.10 or newer is required. Install Python and try again.
pause
exit /b 1
