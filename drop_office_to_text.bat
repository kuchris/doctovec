@echo off
setlocal
title Office to Text

if "%~1"=="" (
  echo Drag one or more Office files, or a folder containing Office files, onto this BAT file.
  echo Folder input is searched recursively, but generated output folders are skipped.
  echo Output is written to text\...\txt\*.txt.
  echo.
  pause
  exit /b 1
)

uv run --python 3.12 --with "markitdown[docx,xlsx,xls,pptx]" "%~dp0Scripts\office_drop_to_text.py" --recursive %*
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo Finished with error code %EXITCODE%.
) else (
  echo Finished successfully.
)
pause
exit /b %EXITCODE%
