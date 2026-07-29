@echo off
REM Quick dev launcher for OpenChem Studio - runs the app straight from
REM source via uv, no packaging/build step needed. Use build.bat once you
REM want a standalone .exe instead.
cd /d "%~dp0"
uv run openchem
if errorlevel 1 pause
