#!/bin/bash

# Script para iniciar API Python (Linux/Mac)

cd "$(dirname "$0")"

# Verificar se Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "Python 3 não encontrado. Por favor, instale Python 3."
    exit 1
fi

# Instalar dependências se necessário
if [ ! -d "venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv venv
fi

echo "Ativando ambiente virtual..."
source venv/bin/activate

echo "Instalando dependências..."
pip install -r requirements.txt

echo "Iniciando API BOIIIWD..."
python boiiiwd_api_improved.py