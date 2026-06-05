@echo off
setlocal EnableDelayedExpansion
title doctovec CLI Installer

set "DOC_DIR=%~dp0"
if "%DOC_DIR:~-1%"=="\" set "DOC_DIR=%DOC_DIR:~0,-1%"
set "MISSING=0"
set "WARNINGS=0"
set "INTERACTIVE=1"
set "OK=[OK]"
set "WARN=[WARN]"
set "MISS=[MISSING]"

if /i "%~1"=="--cli" set "INTERACTIVE=0"
if /i "%~1"=="--no-pause" set "INTERACTIVE=0"
if /i "%~1"=="/cli" set "INTERACTIVE=0"

for /f "delims=" %%E in ('powershell -NoProfile -Command "[char]27" 2^>nul') do set "ESC=%%E"
if defined ESC (
  set "OK=%ESC%[92m[OK]%ESC%[0m"
  set "WARN=%ESC%[93m[WARN]%ESC%[0m"
  set "MISS=%ESC%[91m[MISSING]%ESC%[0m"
)

echo doctovec CLI installer
echo Target:
echo   %DOC_DIR%
echo.

echo Progress [#--] 33%% - Checking uv
echo == uv ==
where uv >nul 2>nul
if errorlevel 1 (
  echo !MISS! uv was not found in PATH.
  choice /C YN /N /M "Install uv with winget now? [Y/N]: "
  if errorlevel 2 (
    echo !WARN! Skipped uv install.
    set /a MISSING+=1
  ) else (
    winget install astral-sh.uv
    if errorlevel 1 (
      echo !MISS! uv install failed.
      set /a MISSING+=1
    ) else (
      echo !OK! uv install command completed. Open a new terminal if uv is still not found.
    )
  )
) else (
  for /f "delims=" %%V in ('uv --version 2^>nul') do echo !OK! uv: %%V
)

echo.
echo Progress [##-] 66%% - Checking LibreOffice
echo == LibreOffice ==
where soffice >nul 2>nul
if errorlevel 1 (
  if exist "C:\Program Files\LibreOffice\program\soffice.exe" (
    echo !OK! LibreOffice: C:\Program Files\LibreOffice\program\soffice.exe
  ) else (
    echo !MISS! LibreOffice soffice.exe was not found.
    choice /C YN /N /M "Install LibreOffice with winget now? [Y/N]: "
    if errorlevel 2 (
      echo !WARN! Skipped LibreOffice install.
      set /a MISSING+=1
    ) else (
      winget install TheDocumentFoundation.LibreOffice
      if errorlevel 1 (
        echo !MISS! LibreOffice install failed.
        set /a MISSING+=1
      ) else (
        echo !OK! LibreOffice install command completed.
      )
    )
  )
) else (
  set "SOFFICE_PATH="
  for /f "delims=" %%S in ('where soffice 2^>nul') do if not defined SOFFICE_PATH set "SOFFICE_PATH=%%S"
  echo !OK! LibreOffice: !SOFFICE_PATH!
)

echo.
echo Progress [###] 100%% - Embedding model
echo == Embedding model ==
where uv >nul 2>nul
if errorlevel 1 (
  echo !MISS! Cannot download model because uv is not available in this terminal.
  set /a MISSING+=1
) else (
  choice /C YN /N /M "Download/warm the DirectML embedding model now? [Y/N]: "
  if errorlevel 2 (
    echo !WARN! Skipped model download.
    set /a WARNINGS+=1
  ) else (
    uv run --directory "%DOC_DIR%\docmemory_tool" --python 3.12 --extra directml python "%DOC_DIR%\Scripts\download_vector_model.py" --directml
    if errorlevel 1 (
      echo !MISS! Model download/warmup failed.
      set /a MISSING+=1
    ) else (
      echo !OK! Model downloaded/warmed without indexing documents.
    )
  )
)

echo.
echo == Install summary ==
if "%MISSING%"=="0" (
  echo Install result: !OK!
) else (
  echo Install result: %MISSING% missing/failed item(s)
)
if "%WARNINGS%"=="0" (
  echo Warnings: !OK! none
) else (
  echo Warnings: %WARNINGS%
)

echo.
if "%INTERACTIVE%"=="1" pause
exit /b %MISSING%
