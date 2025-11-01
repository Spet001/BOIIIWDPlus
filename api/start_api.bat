@echo off
REM Script para iniciar API Python (Windows)

cd /d "%~dp0"

REM Verificar se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo Python não encontrado. Por favor, instale Python 3.
    pause
    exit /b 1
)

REM Criar ambiente virtual se não existir
if not exist "venv" (
    echo Criando ambiente virtual...
    python -m venv venv
)

echo Ativando ambiente virtual...
call venv\Scripts\activate.bat

echo Instalando dependências...
pip install -r requirements.txt

echo Iniciando API BOIIIWD...
python boiiiwd_api_improved.py

pause