import os

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from typing import Dict, Optional, List

import logging

from .server.process_manager import ProcessManager
from .server.file_manager import FileManager

# This is important when running on Windows Git Bash


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set up Flask with static file handling
app = Flask(__name__, static_url_path='')
CORS(app)
# Define base directory and app directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'static', 'app')
COMPONENTS_DIR = os.path.join(BASE_DIR, 'static', 'components')

socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize managers
process_manager = ProcessManager(socketio)
file_manager = FileManager(".")

# Routes
@app.route('/')
def serve_index():
    """Serve the main index.html file"""
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'app'), 'index.html')

@app.route('/components/<path:path>')
def serve_components(path):
    """Serve files from components directory"""
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'components'), path)

@app.route('/app/<path:path>')
def serve_app_files(path):
    """Serve files from app directory"""
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'app'), path)

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (JS, CSS, etc) from app directory by default"""
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'app'), path)

@app.route('/favicon.ico')
def favicon():
    """Handle favicon request"""
    return '', 204  # Return no content status code

@app.route('/api/files', methods=['GET'])
def list_files():
    """List files in a directory"""
    try:
        path = request.args.get('path', '.')
        files = file_manager.list_files(path)
        return jsonify([file.to_dict() for file in files])
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/files/content', methods=['GET'])
def get_file_content():
    """Get content of a specific file"""
    try:
        path = request.args.get('path')
        if not path:
            return jsonify({"error": "Path parameter is required"}), 400
        content = file_manager.get_file_content(path)
        return jsonify({
            "content": content,
            "fileExtension": path.split('.')[-1] if '.' in path else ''
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/files/stats', methods=['POST'])
def get_files_stats():
    """Get statistics for files/directories"""
    try:
        data = request.get_json()
        paths = data.get('paths', [])
        recursive = data.get('recursive', False)
        stats = file_manager.get_files_stats(paths, recursive)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/processes', methods=['GET', 'POST'])
def handle_processes():
    """Handle process listing and creation"""
    if request.method == 'GET':
        return jsonify({"processes": process_manager.list_processes()})
    
    try:
        data = request.get_json()
        command = data.get('command')
        args = data.get('args', [])
        
        if not command:
            return jsonify({"error": "Command is required"}), 400
        
        process_id = process_manager.start_process(command, args)
        return jsonify({"process_id": process_id})
    except Exception as e:
        return jsonify({"detail": str(e)}), 400

@app.route('/api/processes/<process_id>', methods=['GET', 'DELETE'])
def handle_process(process_id):
    """Handle individual process operations"""
    if request.method == 'GET':
        info = process_manager.get_process_info(process_id)
        if info is None:
            return jsonify({"error": "Process not found"}), 404
        return jsonify(info)
    
    if request.method == 'DELETE':
        try:
            process_manager.terminate_process(process_id)
            return jsonify({"status": "terminated"})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

@socketio.on('process_input')
def handle_process_input(data):
    """Handle process input through WebSocket"""
    try:
        process_id = data.get('process_id')
        input_data = data.get('input')
        if not process_id or not input_data:
            raise ValueError("Process ID and input data are required")
        process_manager.send_input(process_id, input_data)
    except Exception as e:
        emit('error', {'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
