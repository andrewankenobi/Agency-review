from flask import Flask, render_template, jsonify, request
import json
import subprocess
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
import threading
import time
import logging
import sys
from datetime import datetime

app = Flask(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Default system prompt path
SYSTEM_PROMPT_PATH = 'system_prompt.txt'
DEFAULT_PROMPT_PATH = 'default_system_prompt.txt'

# Global variables to track refresh status
refresh_status = {
    'status': 'idle',
    'message': '',
    'last_update': None
}

# Lock for thread safety
refresh_lock = threading.Lock()

# Progress tracking
refresh_progress = {
    'status': 'idle',
    'message': '',
    'start_time': None,
    'end_time': None
}

# File to store progress state
PROGRESS_FILE = 'refresh_progress.json'

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

def load_system_prompt(file_path=SYSTEM_PROMPT_PATH):
    try:
        with open(file_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def save_system_prompt(prompt, file_path=SYSTEM_PROMPT_PATH):
    with open(file_path, 'w') as f:
        f.write(prompt)

def revert_to_default():
    try:
        with open(DEFAULT_PROMPT_PATH, 'r') as f:
            default_prompt = f.read().strip()
        save_system_prompt(default_prompt)
        return default_prompt
    except FileNotFoundError:
        return None

def get_agencies():
    """Get the list of agencies from output.json."""
    try:
        # Get the absolute path to output.json
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output.json')
        
        # Check if file exists
        if not os.path.exists(output_path):
            logger.error(f"output.json not found at {output_path}")
            return jsonify([])
        
        # Read and parse the file
        with open(output_path, 'r', encoding='utf-8') as f:
            agencies = json.load(f)
            
        # Validate the data structure
        if not isinstance(agencies, list):
            logger.error("output.json does not contain a list")
            return jsonify([])
            
        return jsonify(agencies)
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing output.json: {str(e)}")
        return jsonify([])
    except Exception as e:
        logger.error(f"Error reading output.json: {str(e)}")
        return jsonify([])

def save_progress():
    """Save progress state to file."""
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(refresh_progress, f)
        logger.info(f"Progress saved: {refresh_progress['status']} - {refresh_progress['message']}")
    except Exception as e:
        logger.error(f"Error saving progress: {str(e)}")

def load_progress():
    """Load progress state from file."""
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded progress: {data['status']} - {data['message']}")
                return data
    except Exception as e:
        logger.error(f"Error loading progress: {str(e)}")
    return {
        'status': 'idle',
        'message': '',
        'start_time': None,
        'end_time': None
    }

# Load initial progress state
refresh_progress = load_progress()
logger.info(f"Initial progress state: {refresh_progress['status']}")

def run_refresh():
    """Run the refresh process in a separate thread"""
    global refresh_status
    
    try:
        with refresh_lock:
            refresh_status['status'] = 'running'
            refresh_status['message'] = 'Starting data refresh...'
            refresh_status['last_update'] = datetime.now()
        
        # Run the main.py script
        process = subprocess.Popen(
            ['python3', 'main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Stream output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                with refresh_lock:
                    refresh_status['message'] = output.strip()
                    refresh_status['last_update'] = datetime.now()
        
        # Check for errors
        return_code = process.poll()
        if return_code == 0:
            with refresh_lock:
                refresh_status['status'] = 'complete'
                refresh_status['message'] = 'Data refresh completed successfully'
                refresh_status['last_update'] = datetime.now()
        else:
            error_output = process.stderr.read()
            with refresh_lock:
                refresh_status['status'] = 'error'
                refresh_status['message'] = f'Error: {error_output}'
                refresh_status['last_update'] = datetime.now()
    
    except Exception as e:
        with refresh_lock:
            refresh_status['status'] = 'error'
            refresh_status['message'] = f'Error: {str(e)}'
            refresh_status['last_update'] = datetime.now()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/agencies')
def get_agencies_route():
    return get_agencies()

def cleanup_progress():
    """Reset progress state to idle."""
    global refresh_progress
    refresh_progress = {
        'status': 'idle',
        'message': '',
        'start_time': None,
        'end_time': None
    }
    save_progress()
    logger.info("Progress state reset to idle")

# Initialize progress state on server startup
cleanup_progress()

@app.route('/api/refresh/reset', methods=['POST'])
def reset_refresh():
    """Force reset the refresh state."""
    try:
        cleanup_progress()
        return jsonify({'status': 'success', 'message': 'Refresh state reset'})
    except Exception as e:
        logger.error(f"Error resetting refresh state: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/refresh/start', methods=['POST'])
def start_refresh():
    """Start the data refresh process"""
    try:
        with refresh_lock:
            if refresh_status['status'] == 'running':
                return jsonify({
                    'status': 'error',
                    'message': 'A refresh is already in progress'
                }), 400
            
            # Start the refresh process in a separate thread
            thread = threading.Thread(target=run_refresh)
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'status': 'started',
                'message': 'Refresh process started'
            })
    
    except Exception as e:
        logger.error(f"Error starting refresh: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error starting refresh: {str(e)}'
        }), 500

@app.route('/api/refresh/progress')
def get_progress():
    """Get the current status of the refresh process"""
    try:
        with refresh_lock:
            return jsonify({
                'status': refresh_status['status'],
                'message': refresh_status['message'],
                'last_update': refresh_status['last_update'].isoformat() if refresh_status['last_update'] else None
            })
    
    except Exception as e:
        logger.error(f"Error getting progress: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error getting progress: {str(e)}'
        }), 500

@app.route('/api/system-prompt', methods=['GET'])
def get_system_prompt():
    prompt = load_system_prompt()
    return jsonify({'prompt': prompt})

@app.route('/api/system-prompt', methods=['POST'])
def update_system_prompt():
    data = request.json
    if 'prompt' not in data:
        return jsonify({'error': 'No prompt provided'}), 400
    
    save_system_prompt(data['prompt'])
    return jsonify({'status': 'success'})

@app.route('/api/system-prompt/revert', methods=['POST'])
def revert_system_prompt():
    default_prompt = revert_to_default()
    if default_prompt is None:
        return jsonify({'error': 'Default prompt not found'}), 404
    return jsonify({'prompt': default_prompt})

@app.route('/api/raw-data/<filename>')
def get_raw_data(filename):
    try:
        # Get the absolute path to the raw data file
        raw_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw', filename)
        
        # Check if file exists
        if not os.path.exists(raw_data_path):
            logger.error(f"Raw data file not found at {raw_data_path}")
            return jsonify({'error': 'Raw data file not found'}), 404
            
        # Read and return the file content
        with open(raw_data_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return content, 200, {'Content-Type': 'text/plain'}
            
    except Exception as e:
        logger.error(f"Error reading raw data file {filename}: {str(e)}")
        return jsonify({'error': 'Failed to read raw data file'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 