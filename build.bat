@echo off
echo ==============================================
echo    BOIIIWD Electron - Build Script
echo ==============================================
echo.

REM Verificar se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python não encontrado. Por favor, instale Python 3.
    pause
    exit /b 1
)

REM Verificar se Node.js está instalado
npm --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js/npm não encontrado. Por favor, instale Node.js.
    pause
    exit /b 1
)

echo ✅ Python e Node.js encontrados!
echo.

REM Executar script de build
echo 🚀 Iniciando processo de build...
python build_electron.py

if errorlevel 1 (
    echo.
    echo ❌ Build falhou!
    pause
    exit /b 1
) else (
    echo.
    echo 🎉 Build concluído com sucesso!
    echo.
    echo 📁 Verifique a pasta 'dist' para os arquivos finais.
    echo.
)

pause