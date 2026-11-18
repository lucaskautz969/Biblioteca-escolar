@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Backup manual da biblioteca
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Solicite apoio tecnico.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "backup_facil.py"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
