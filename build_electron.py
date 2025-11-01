# Build Script for BOIIIWD Electron
# Empacota Python com PyInstaller e Electron com electron-builder

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
API_DIR = PROJECT_ROOT / "api"
ELECTRON_DIR = PROJECT_ROOT / "electron"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"

def run_command(cmd, cwd=None):
    """Executar comando e capturar saída"""
    print(f"Executando: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Erro ao executar comando: {cmd}")
        print(f"STDERR: {result.stderr}")
        return False
    
    print(f"STDOUT: {result.stdout}")
    return True

def clean_build_dirs():
    """Limpar diretórios de build anteriores"""
    print("🧹 Limpando diretórios de build...")
    
    dirs_to_clean = [DIST_DIR, BUILD_DIR, ELECTRON_DIR / "dist", API_DIR / "dist", API_DIR / "build"]
    
    for dir_path in dirs_to_clean:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"   Removido: {dir_path}")

def build_python_api():
    """Empacotar API Python com PyInstaller"""
    print("🐍 Empacotando API Python...")
    
    # Verificar se PyInstaller está instalado
    try:
        subprocess.run(["pyinstaller", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PyInstaller não encontrado. Instalando...")
        if not run_command("pip install pyinstaller"):
            return False
    
    # Criar spec file para PyInstaller
    spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['boiiiwd_api_improved.py'],
    pathex=['{API_DIR.absolute()}'],
    binaries=[],
    datas=[
        ('requirements.txt', '.'),
        ('../boiiiwd_package', 'boiiiwd_package'),
    ],
    hiddenimports=[
        'flask',
        'flask_cors',
        'requests',
        'beautifulsoup4',
        'PIL',
        'json',
        'threading',
        'time',
        'os',
        'sys',
        'pathlib',
        'shutil',
        'subprocess'
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='boiiiwd_api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
"""
    
    spec_file = API_DIR / "boiiiwd_api.spec"
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    # Executar PyInstaller
    cmd = f"pyinstaller --clean --onefile boiiiwd_api.spec"
    if not run_command(cmd, cwd=API_DIR):
        return False
    
    print("✅ API Python empacotada com sucesso!")
    return True

def install_electron_deps():
    """Instalar dependências do Electron"""
    print("📦 Instalando dependências do Electron...")
    
    # Verificar se npm está disponível
    try:
        subprocess.run(["npm", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ npm não encontrado. Por favor, instale Node.js.")
        return False
    
    if not run_command("npm install", cwd=ELECTRON_DIR):
        return False
    
    print("✅ Dependências do Electron instaladas!")
    return True

def build_electron_app():
    """Empacotar aplicação Electron"""
    print("⚡ Empacotando aplicação Electron...")
    
    # Copiar API empacotada para recursos do Electron
    api_exe = API_DIR / "dist" / "boiiiwd_api.exe"
    electron_resources = ELECTRON_DIR / "resources"
    
    if not api_exe.exists():
        print("❌ API Python não encontrada. Execute build_python_api() primeiro.")
        return False
    
    # Criar diretório de recursos
    electron_resources.mkdir(exist_ok=True)
    
    # Copiar API
    shutil.copy2(api_exe, electron_resources / "boiiiwd_api.exe")
    print(f"   API copiada para: {electron_resources}")
    
    # Copiar boiiiwd_package
    boiiiwd_package_src = PROJECT_ROOT / "boiiiwd_package"
    boiiiwd_package_dst = electron_resources / "boiiiwd_package"
    
    if boiiiwd_package_src.exists():
        if boiiiwd_package_dst.exists():
            shutil.rmtree(boiiiwd_package_dst)
        shutil.copytree(boiiiwd_package_src, boiiiwd_package_dst)
        print(f"   boiiiwd_package copiado para: {boiiiwd_package_dst}")
    
    # Build Electron
    if not run_command("npm run build", cwd=ELECTRON_DIR):
        return False
    
    print("✅ Aplicação Electron empacotada com sucesso!")
    return True

def create_installer():
    """Criar instalador final"""
    print("📦 Criando instalador final...")
    
    # O electron-builder já cria o instalador
    # Copiar para diretório de distribuição principal
    electron_dist = ELECTRON_DIR / "dist"
    
    if not electron_dist.exists():
        print("❌ Distribuição do Electron não encontrada.")
        return False
    
    # Criar diretório de distribuição principal
    DIST_DIR.mkdir(exist_ok=True)
    
    # Copiar todos os arquivos de distribuição
    for item in electron_dist.iterdir():
        if item.is_file():
            shutil.copy2(item, DIST_DIR)
            print(f"   Copiado: {item.name}")
        elif item.is_dir() and item.name != "win-unpacked":
            shutil.copytree(item, DIST_DIR / item.name, dirs_exist_ok=True)
            print(f"   Copiado diretório: {item.name}")
    
    print("✅ Instalador criado com sucesso!")
    return True

def main():
    """Processo principal de build"""
    print("🚀 Iniciando build do BOIIIWD Electron...")
    print("=" * 50)
    
    try:
        # 1. Limpar builds anteriores
        clean_build_dirs()
        
        # 2. Build API Python
        if not build_python_api():
            print("❌ Falha ao empacotar API Python")
            return False
        
        # 3. Instalar dependências Electron
        if not install_electron_deps():
            print("❌ Falha ao instalar dependências Electron")
            return False
        
        # 4. Build aplicação Electron
        if not build_electron_app():
            print("❌ Falha ao empacotar aplicação Electron")
            return False
        
        # 5. Criar instalador
        if not create_installer():
            print("❌ Falha ao criar instalador")
            return False
        
        print("=" * 50)
        print("🎉 Build concluído com sucesso!")
        print(f"📁 Arquivos de distribuição em: {DIST_DIR.absolute()}")
        
        # Listar arquivos criados
        if DIST_DIR.exists():
            print("\n📋 Arquivos criados:")
            for item in DIST_DIR.iterdir():
                if item.is_file():
                    size = item.stat().st_size / (1024 * 1024)  # MB
                    print(f"   {item.name} ({size:.1f} MB)")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro durante o build: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)