@echo off
setlocal

set "INTERACTIVE=1"
if /i "%~1"=="--cli" set "INTERACTIVE=0"
if /i "%~1"=="--no-pause" set "INTERACTIVE=0"
if /i "%~1"=="/cli" set "INTERACTIVE=0"

set "TOOL_DIR=%~dp0docmemory_tool"
set "DOC_DIR=%~dp0"
if "%DOC_DIR:~-1%"=="\" set "DOC_DIR=%DOC_DIR:~0,-1%"
if not exist "%TOOL_DIR%\pyproject.toml" (
  echo DocMemory tool folder was not found:
  echo   %TOOL_DIR%
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)
if not exist "%DOC_DIR%\.docmemory\config.json" (
  set "DOCMEMORY_COMMAND=init"
) else (
  set "DOCMEMORY_COMMAND=sync"
)
if not defined DOCMEMORY_DML_MODEL set "DOCMEMORY_DML_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
if not defined DOCMEMORY_DML_BATCH_SIZE set "DOCMEMORY_DML_BATCH_SIZE=32"

echo DocMemory DirectML text vector sync
echo Target:
echo   %DOC_DIR%
echo.
echo Model:
echo   %DOCMEMORY_DML_MODEL%
echo Batch size:
echo   %DOCMEMORY_DML_BATCH_SIZE%
echo Command:
echo   %DOCMEMORY_COMMAND%
echo.

pushd "%TOOL_DIR%"
uv run --python 3.12 --extra directml docmemory-dml %DOCMEMORY_COMMAND% "%DOC_DIR%" --vector --model "%DOCMEMORY_DML_MODEL%"
set "RC=%ERRORLEVEL%"
popd

echo.
if not "%RC%"=="0" (
  echo Failed with exit code %RC%.
) else (
  echo Done.
)
if "%INTERACTIVE%"=="1" pause
exit /b %RC%
