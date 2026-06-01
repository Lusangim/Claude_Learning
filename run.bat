@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- Test Report Analyzer: double-click launcher for Windows ---
REM Drag a FOLDER of PDFs (or selected PDF files) onto this file,
REM or just double-click it to use the "reports" folder.

REM 1) Find Python (the "py" launcher, or "python").
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY goto :nopython

REM 2) One-time install of dependencies (needs internet the first time).
if not exist ".deps_installed" (
  echo Installing dependencies ^(one-time, needs internet^)...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 goto :piperr
  echo ok> .deps_installed
)

REM 3) Decide what to analyze: dropped items, else the "reports" folder.
set "TARGET=%*"
if not defined TARGET (
  if not exist "reports" mkdir reports
  set "TARGET=reports"
  echo.
  echo No folder was dropped onto this file.
  echo Put your PDF reports in this folder, then run again:
  echo    %cd%\reports
  echo.
)

REM 4) Run it. Output goes to the "output" folder.
if not exist "output" mkdir output
echo Analyzing: !TARGET!
echo.
%PY% -m report_analyzer !TARGET! --xlsx "output\TR_Summary.xlsx" --csv "output\summary.csv" --print
if errorlevel 1 goto :runerr

echo.
echo Done. Opening the output folder...
start "" "%cd%\output"
pause
exit /b 0

:nopython
echo.
echo Python is not installed.
echo   1^) Open https://www.python.org/downloads/ and download Python 3.
echo   2^) Run the installer and TICK the box "Add python.exe to PATH".
echo   3^) Double-click this run.bat again.
echo.
pause
exit /b 1

:piperr
echo.
echo Could not install dependencies. Check your internet connection and try again.
echo.
pause
exit /b 1

:runerr
echo.
echo Something went wrong while analyzing. See the messages above.
echo.
pause
exit /b 1
