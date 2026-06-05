@echo off
setlocal
chcp 65001 >nul

where uv >nul 2>nul
if errorlevel 1 (
    echo uv was not found in PATH.
    echo Please install uv or run this from a shell where uv works.
    echo.
    pause
    exit /b 1
)

echo Remove Office/PDF open-password protection
echo Passwords are read only from Config\pass.txt
echo If Config\pass.txt has no passwords, this step is skipped.
echo.

if "%~1"=="" (
    echo No file/folder was dropped. Scanning this folder:
    echo %~dp0
    echo.
    uv run "%~dp0Scripts\remove_passwords.py" "%~dp0"
) else (
    echo Dropped items:
    for %%I in (%*) do echo   %%~fI
    echo.
    uv run "%~dp0Scripts\remove_passwords.py" %*
)

set EXIT_CODE=%ERRORLEVEL%
echo.
if "%EXIT_CODE%"=="0" (
    echo Done.
) else (
    echo Finished with errors. Exit code: %EXIT_CODE%
)
echo.
pause
exit /b %EXIT_CODE%
