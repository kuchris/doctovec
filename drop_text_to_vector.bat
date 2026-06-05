@echo off
setlocal

set "TOOL_DIR=%~dp0docmemory_tool"
set "DOC_DIR=%~dp0"
if "%DOC_DIR:~-1%"=="\" set "DOC_DIR=%DOC_DIR:~0,-1%"
set "DOCMEMORY_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

if not exist "%TOOL_DIR%\pyproject.toml" (
  echo DocMemory tool folder was not found:
  echo   %TOOL_DIR%
  pause
  exit /b 1
)
if not exist "%DOC_DIR%\.docmemory\config.json" (
  set "DOCMEMORY_COMMAND=init"
) else (
  set "DOCMEMORY_COMMAND=sync"
)

echo DocMemory text vector sync
echo Target:
echo   %DOC_DIR%
echo Model:
echo   %DOCMEMORY_MODEL%
echo Command:
echo   %DOCMEMORY_COMMAND%
echo.

pushd "%TOOL_DIR%"
uv run --python 3.12 --extra vector docmemory %DOCMEMORY_COMMAND% "%DOC_DIR%" --vector --model "%DOCMEMORY_MODEL%"
set "RC=%ERRORLEVEL%"
popd

echo.
if not "%RC%"=="0" (
  echo Failed with exit code %RC%.
) else (
  echo Done.
)
pause
exit /b %RC%
