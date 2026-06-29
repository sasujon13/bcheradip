@echo off
cd /d "%~dp0.."
python scripts\build-manual.py %*
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
echo Open Angular: http://localhost:4200/ailt
echo Static preview: %CD%\..\..\fcheradip\src\assets\ailt\ailt.html
