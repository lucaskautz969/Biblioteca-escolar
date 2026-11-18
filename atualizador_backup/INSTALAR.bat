@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" "instalar.py"
  goto fim
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "instalar.py"
  goto fim
)
where python >nul 2>nul
if not errorlevel 1 (
  python "instalar.py"
  goto fim
)
echo Python nao encontrado. Coloque esta pasta dentro da pasta do sistema e tente novamente.
:fim
pause
