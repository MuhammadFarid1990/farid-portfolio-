@echo off
REM Wrapper that loops the agent so the "Pull & Restart" button can
REM exit with code 42 and we just start it back up.

:loop
echo.
echo === Starting job agent (Ctrl+C to stop) ===
echo.
python agent.py
if %ERRORLEVEL% == 42 (
    echo.
    echo === Restart requested by dashboard, relaunching... ===
    echo.
    timeout /t 2 /nobreak >nul
    goto loop
)
echo.
echo === Agent exited with code %ERRORLEVEL%. Done. ===
pause
