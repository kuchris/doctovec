@echo off
setlocal
title Generate Document Index

set "DOC_DIR=%~dp0"
if "%DOC_DIR:~-1%"=="\" set "DOC_DIR=%DOC_DIR:~0,-1%"

uv run --python 3.12 "%DOC_DIR%\Scripts\generate_document_index.py" --root "%DOC_DIR%"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo Failed with exit code %RC%.
) else (
  echo Done.
)
pause
exit /b %RC%
