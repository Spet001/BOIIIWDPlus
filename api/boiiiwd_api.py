"""
BOIIIWD API - Flask Backend para Electron Frontend
Expõe toda a lógica do BOIIIWD via API REST
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import threading
import time
import os
import sys
import subprocess
import webbrowser
from pathlib import Path

# Adicionar o caminho do projeto para importar módulos existentes
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "boiiiwd_package"))
sys.path.insert(0, str(project_root / "boiiiwd_package" / "src"))

# Importar módulos existentes do BOIIIWD
from src.helpers import *
from src.library_tab import LibraryTab
from src.settings_tab import SettingsTab
import src.shared_vars as shared_vars

app = Flask(__name__)
CORS(app)  # Permitir requests do Electron

# Estado global da aplicação
app_state = {
    'download_progress': 0,
    'download_status': 'idle',
    'current_download': None,
    'queue': [],
    'library_items': [],
    'downloading': False,
    'download_speed': '0 KB/s',
    'file_size': '0KB',
    'steam_logged_in': False
}

# Instâncias das classes existentes (simuladas para API)
library_manager = None
settings_manager = None

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar se a API está funcionando"""
    return jsonify({'status': 'healthy', 'message': 'BOIIIWD API is running'})

@app.route('/api/login', methods=['POST'])
def steam_login():
    """Endpoint para login no Steam"""
    try:
        data = request.get_json()
        username = data.get('username', '')
        password = data.get('password', '')
        
        # Implementar lógica de login usando funções existentes
        # Por enquanto, simular sucesso
        app_state['steam_logged_in'] = True
        save_config("login_cached", "on")
        
        return jsonify({
            'success': True,
            'message': 'Login realizado com sucesso',
            'logged_in': True
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro no login: {str(e)}',
            'logged_in': False
        }), 500

@app.route('/api/download', methods=['POST'])
def download_workshop_item():
    """Endpoint para baixar item por Workshop ID"""
    try:
        data = request.get_json()
        workshop_id = data.get('workshop_id', '').strip()
        
        if not workshop_id:
            return jsonify({
                'success': False,
                'message': 'Workshop ID é obrigatório'
            }), 400
            
        # Validar se é um ID válido
        if not workshop_id.isdigit():
            try:
                workshop_id = extract_workshop_id(workshop_id).strip()
                if not workshop_id.isdigit():
                    raise ValueError("ID inválido")
            except:
                return jsonify({
                    'success': False,
                    'message': 'Workshop ID/Link inválido'
                }), 400
        
        # Verificar se já está baixando
        if app_state['downloading']:
            return jsonify({
                'success': False,
                'message': 'Download já em andamento'
            }), 409
        
        # Iniciar download em thread separada
        def start_download():
            app_state['downloading'] = True
            app_state['current_download'] = workshop_id
            app_state['download_status'] = 'downloading'
            
            try:
                # Aqui você usaria a lógica existente de download
                # Por enquanto, simular um download
                for i in range(101):
                    if not app_state['downloading']:  # Se parado
                        break
                    app_state['download_progress'] = i
                    time.sleep(0.1)
                
                if app_state['downloading']:  # Se completou sem ser parado
                    app_state['download_status'] = 'completed'
                    # Atualizar biblioteca
                    load_library_items()
                else:
                    app_state['download_status'] = 'stopped'
                    
            except Exception as e:
                app_state['download_status'] = 'error'
                app_state['error_message'] = str(e)
            finally:
                app_state['downloading'] = False
                app_state['current_download'] = None
        
        threading.Thread(target=start_download, daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': f'Download iniciado para ID: {workshop_id}',
            'workshop_id': workshop_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao iniciar download: {str(e)}'
        }), 500

@app.route('/api/download/stop', methods=['POST'])
def stop_download():
    """Endpoint para parar download atual"""
    try:
        if app_state['downloading']:
            app_state['downloading'] = False
            app_state['download_status'] = 'stopped'
            # Aqui você chamaria kill_steamcmd() e outras funções de parada
            
        return jsonify({
            'success': True,
            'message': 'Download parado'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao parar download: {str(e)}'
        }), 500

@app.route('/api/download/status', methods=['GET'])
def get_download_status():
    """Endpoint para obter status do download atual"""
    return jsonify({
        'downloading': app_state['downloading'],
        'progress': app_state['download_progress'],
        'status': app_state['download_status'],
        'current_download': app_state['current_download'],
        'speed': app_state['download_speed'],
        'file_size': app_state['file_size']
    })

@app.route('/api/queue', methods=['GET'])
def get_queue():
    """Endpoint para obter fila de downloads"""
    return jsonify({
        'queue': app_state['queue'],
        'count': len(app_state['queue'])
    })

@app.route('/api/queue', methods=['POST'])
def add_to_queue():
    """Endpoint para adicionar itens à fila"""
    try:
        data = request.get_json()
        items = data.get('items', [])
        
        if isinstance(items, str):
            # Se for string, dividir por linha ou vírgula
            items = [item.strip() for item in items.replace(',', '\n').split('\n') if item.strip()]
        
        added_items = []
        for item in items:
            if item.isdigit() and item not in app_state['queue']:
                app_state['queue'].append(item)
                added_items.append(item)
        
        return jsonify({
            'success': True,
            'message': f'{len(added_items)} itens adicionados à fila',
            'added_items': added_items,
            'queue': app_state['queue']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao adicionar à fila: {str(e)}'
        }), 500

@app.route('/api/queue', methods=['DELETE'])
def clear_queue():
    """Endpoint para limpar fila"""
    app_state['queue'] = []
    return jsonify({
        'success': True,
        'message': 'Fila limpa'
    })

@app.route('/api/queue/process', methods=['POST'])
def process_queue():
    """Endpoint para processar fila de downloads"""
    try:
        if app_state['downloading']:
            return jsonify({
                'success': False,
                'message': 'Download já em andamento'
            }), 409
            
        if not app_state['queue']:
            return jsonify({
                'success': False,
                'message': 'Fila vazia'
            }), 400
        
        def process_queue_items():
            app_state['downloading'] = True
            
            while app_state['queue'] and app_state['downloading']:
                current_item = app_state['queue'].pop(0)
                app_state['current_download'] = current_item
                app_state['download_status'] = 'downloading'
                
                # Simular download do item
                for i in range(101):
                    if not app_state['downloading']:
                        break
                    app_state['download_progress'] = i
                    time.sleep(0.05)
                
                if app_state['downloading']:
                    app_state['download_status'] = 'completed'
                    time.sleep(1)
            
            app_state['downloading'] = False
            app_state['current_download'] = None
            app_state['download_status'] = 'idle'
        
        threading.Thread(target=process_queue_items, daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': 'Processamento da fila iniciado'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao processar fila: {str(e)}'
        }), 500

def load_library_items():
    """Carregar itens da biblioteca"""
    try:
        # Usar lógica existente para carregar biblioteca
        destination_folder = check_config("DestinationFolder", "")
        if not destination_folder:
            app_state['library_items'] = []
            return
            
        # Simular carregamento da biblioteca
        # Na implementação real, usar a lógica da LibraryTab
        items = []
        # items = library_manager.load_items(destination_folder) se existisse
        
        app_state['library_items'] = items
        
    except Exception as e:
        print(f"Erro ao carregar biblioteca: {e}")
        app_state['library_items'] = []

@app.route('/api/library', methods=['GET'])
def get_library():
    """Endpoint para obter biblioteca de mods instalados"""
    load_library_items()
    return jsonify({
        'items': app_state['library_items'],
        'count': len(app_state['library_items'])
    })

@app.route('/api/library/refresh', methods=['POST'])
def refresh_library():
    """Endpoint para atualizar biblioteca"""
    load_library_items()
    return jsonify({
        'success': True,
        'message': 'Biblioteca atualizada',
        'items': app_state['library_items'],
        'count': len(app_state['library_items'])
    })

@app.route('/api/library/remove', methods=['DELETE'])
def remove_library_item():
    """Endpoint para remover item da biblioteca"""
    try:
        data = request.get_json()
        item_id = data.get('item_id', '')
        
        if not item_id:
            return jsonify({
                'success': False,
                'message': 'ID do item é obrigatório'
            }), 400
        
        # Aqui você implementaria a remoção usando lógica existente
        # Por enquanto, simular remoção
        
        return jsonify({
            'success': True,
            'message': f'Item {item_id} removido da biblioteca'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao remover item: {str(e)}'
        }), 500

@app.route('/api/library/fix-compatibility', methods=['POST'])
def fix_bo3_enhanced_compatibility():
    """Endpoint para renomear pastas para compatibilidade com BO3Enhanced"""
    try:
        data = request.get_json()
        items = data.get('items', [])  # Lista de IDs ou 'all' para todos
        
        destination_folder = check_config("DestinationFolder", "")
        if not destination_folder:
            return jsonify({
                'success': False,
                'message': 'Pasta de destino não configurada'
            }), 400
        
        fixed_items = []
        errors = []
        
        # Obter lista de pastas no diretório de workshop
        workshop_path = os.path.join(destination_folder, "usermaps")
        if not os.path.exists(workshop_path):
            workshop_path = os.path.join(destination_folder, "mods")
            
        if not os.path.exists(workshop_path):
            return jsonify({
                'success': False,
                'message': 'Diretório de workshop não encontrado'
            }), 400
        
        # Se 'all', processar todas as pastas com IDs numéricos
        if items == 'all' or (isinstance(items, list) and 'all' in items):
            items = [folder for folder in os.listdir(workshop_path) 
                    if os.path.isdir(os.path.join(workshop_path, folder)) and folder.isdigit()]
        
        for item_id in items:
            try:
                item_path = os.path.join(workshop_path, str(item_id))
                if not os.path.exists(item_path):
                    errors.append(f"Pasta {item_id} não encontrada")
                    continue
                
                # Procurar workshop.json
                workshop_json_path = os.path.join(item_path, "zone", "workshop.json")
                if not os.path.exists(workshop_json_path):
                    errors.append(f"workshop.json não encontrado para {item_id}")
                    continue
                
                # Ler FolderName do workshop.json
                with open(workshop_json_path, 'r', encoding='utf-8') as f:
                    workshop_data = json.load(f)
                
                folder_name = workshop_data.get('FolderName', '')
                if not folder_name:
                    errors.append(f"FolderName não encontrado no workshop.json para {item_id}")
                    continue
                
                # Renomear pasta se necessário
                new_path = os.path.join(workshop_path, folder_name)
                if item_path != new_path:
                    if os.path.exists(new_path):
                        errors.append(f"Pasta {folder_name} já existe para {item_id}")
                        continue
                    
                    os.rename(item_path, new_path)
                    fixed_items.append({
                        'id': item_id,
                        'old_name': str(item_id),
                        'new_name': folder_name
                    })
                
            except Exception as e:
                errors.append(f"Erro ao processar {item_id}: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'{len(fixed_items)} itens renomeados com sucesso',
            'fixed_items': fixed_items,
            'errors': errors,
            'fixed_count': len(fixed_items),
            'error_count': len(errors)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao corrigir compatibilidade: {str(e)}'
        }), 500

@app.route('/api/workshop/info', methods=['GET'])
def get_workshop_info():
    """Endpoint para obter informações de item do workshop"""
    try:
        workshop_id = request.args.get('id', '').strip()
        
        if not workshop_id:
            return jsonify({
                'success': False,
                'message': 'Workshop ID é obrigatório'
            }), 400
        
        if not workshop_id.isdigit():
            try:
                workshop_id = extract_workshop_id(workshop_id).strip()
                if not workshop_id.isdigit():
                    raise ValueError("ID inválido")
            except:
                return jsonify({
                    'success': False,
                    'message': 'Workshop ID/Link inválido'
                }), 400
        
        # Aqui você usaria a lógica existente para obter info do workshop
        # Por enquanto, retornar dados simulados
        workshop_info = {
            'id': workshop_id,
            'title': f'Workshop Item {workshop_id}',
            'description': 'Descrição do item...',
            'size': '150 MB',
            'type': 'Map',
            'author': 'Autor',
            'rating': '4.5',
            'created': '2023-01-01',
            'updated': '2023-06-01',
            'preview_url': '',
            'workshop_url': f'https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}'
        }
        
        return jsonify({
            'success': True,
            'info': workshop_info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao obter informações: {str(e)}'
        }), 500

@app.route('/api/workshop/browse', methods=['POST'])
def open_workshop_browser():
    """Endpoint para abrir navegador do Workshop Steam integrado"""
    try:
        data = request.get_json()
        game_id = data.get('game_id', '311210')  # BO3 por padrão
        
        # URL do workshop
        workshop_url = f"https://steamcommunity.com/app/{game_id}/workshop/"
        
        # Por enquanto, abrir no navegador padrão
        # No futuro, pode ser integrado no próprio Electron
        webbrowser.open(workshop_url)
        
        return jsonify({
            'success': True,
            'message': 'Navegador do Workshop aberto',
            'url': workshop_url
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao abrir navegador: {str(e)}'
        }), 500

@app.route('/api/updates/check', methods=['GET'])
def check_for_updates():
    """Endpoint para verificar atualizações"""
    try:
        # Usar função existente
        latest_version = get_latest_release_version()
        current_version = "1.0.0"  # Obter versão atual
        
        has_update = latest_version and latest_version != current_version
        
        return jsonify({
            'has_update': has_update,
            'current_version': current_version,
            'latest_version': latest_version,
            'update_available': has_update
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao verificar atualizações: {str(e)}'
        }), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Endpoint para obter configurações"""
    try:
        settings = {
            'destination_folder': check_config("DestinationFolder", ""),
            'steamcmd_path': check_config("SteamCMDPath", ""),
            'game_executable': check_config("GameExecutable", "BlackOps3"),
            'launch_parameters': check_config("LaunchParameters", ""),
            'appearance': check_config("appearance", "Dark"),
            'scaling': check_config("scaling", "1.0"),
            'continuous_download': check_config("continuous_download", "on"),
            'clean_on_finish': check_config("clean_on_finish", "on"),
            'console': check_config("console", "off"),
            'estimated_progress': check_config("estimated_progress", "on"),
            'skip_already_installed': check_config("skip_already_installed", "on")
        }
        
        return jsonify({
            'success': True,
            'settings': settings
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao obter configurações: {str(e)}'
        }), 500

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Endpoint para salvar configurações"""
    try:
        data = request.get_json()
        settings = data.get('settings', {})
        
        # Salvar cada configuração
        for key, value in settings.items():
            if key == 'destination_folder':
                save_config("DestinationFolder", value)
            elif key == 'steamcmd_path':
                save_config("SteamCMDPath", value)
            elif key == 'game_executable':
                save_config("GameExecutable", value)
            elif key == 'launch_parameters':
                save_config("LaunchParameters", value)
            elif key == 'appearance':
                save_config("appearance", value)
            elif key == 'scaling':
                save_config("scaling", value)
            elif key == 'continuous_download':
                save_config("continuous_download", value)
            elif key == 'clean_on_finish':
                save_config("clean_on_finish", value)
            elif key == 'console':
                save_config("console", value)
            elif key == 'estimated_progress':
                save_config("estimated_progress", value)
            elif key == 'skip_already_installed':
                save_config("skip_already_installed", value)
        
        return jsonify({
            'success': True,
            'message': 'Configurações salvas com sucesso'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao salvar configurações: {str(e)}'
        }), 500

@app.route('/api/game/launch', methods=['POST'])
def launch_game():
    """Endpoint para iniciar o jogo"""
    try:
        destination_folder = check_config("DestinationFolder", "")
        game_executable = check_config("GameExecutable", "BlackOps3")
        launch_parameters = check_config("LaunchParameters", "")
        
        # Usar função existente launch_game_func
        # launch_game_func(destination_folder, game_executable, launch_parameters)
        
        return jsonify({
            'success': True,
            'message': 'Jogo iniciado'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao iniciar jogo: {str(e)}'
        }), 500

def run_api_server(host='127.0.0.1', port=5000, debug=False):
    """Iniciar servidor da API"""
    print(f"Iniciando BOIIIWD API em http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == '__main__':
    # Inicializar estado da aplicação
    load_library_items()
    
    # Iniciar servidor
    run_api_server(debug=True)