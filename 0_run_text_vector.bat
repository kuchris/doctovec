@echo off
setlocal
title Office Text Vector Index

set "DOC_DIR=%~dp0"
if "%DOC_DIR:~-1%"=="\" set "DOC_DIR=%DOC_DIR:~0,-1%"

if "%~1"=="" (
  set "TARGET_ARGS=%DOC_DIR%"
) else (
  set "TARGET_ARGS=%*"
)

echo Step 1/3: Office to text
uv run --python 3.12 --with "markitdown[docx,xlsx,xls,pptx]" "%DOC_DIR%\Scripts\office_drop_to_text.py" --recursive %TARGET_ARGS%
if errorlevel 1 (
  echo.
  echo Office to text failed.
  pause
  exit /b 1
)

echo.
echo Step 2/3: Text to vector
call "%DOC_DIR%\drop_text_to_vector_dml.bat"
set "VECTOR_RC=%ERRORLEVEL%"
if not "%VECTOR_RC%"=="0" (
  echo.
  echo Text to vector failed.
  pause
  exit /b %VECTOR_RC%
)

echo.
echo Step 3/3: Document index
call "%DOC_DIR%\generate_document_index.bat"
exit /b %ERRORLEVEL%
