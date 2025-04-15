from flask import Flask, render_template, jsonify, request
import json
import subprocess
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
import threading
import time

app = Flask(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Default system prompt path
SYSTEM_PROMPT_PATH = 'system_prompt.txt'
DEFAULT_PROMPT_PATH = 'default_system_prompt.txt'

# Progress tracking
refresh_progress = {
    'status': 'idle',
    'message': '',
    'start_time': None,
    'end_time': None
}

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

def run_main_script():
    try:
        refresh_progress['status'] = 'running'
        refresh_progress['start_time'] = time.time()
        refresh_progress['message'] = 'Starting data refresh...'
        
        # Run main.py and capture output
        process = subprocess.Popen(
            ['python', 'main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Read output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                refresh_progress['message'] = output.strip()
        
        # Check for errors
        _, stderr = process.communicate()
        if process.returncode != 0:
            refresh_progress['status'] = 'error'
            refresh_progress['message'] = f'Error: {stderr}'
        else:
            refresh_progress['status'] = 'complete'
            refresh_progress['message'] = 'Data refresh completed successfully'
        
        refresh_progress['end_time'] = time.time()
        
    except Exception as e:
        refresh_progress['status'] = 'error'
        refresh_progress['message'] = f'Error: {str(e)}'
        refresh_progress['end_time'] = time.time()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/agencies')
def get_agencies():
    try:
        with open('output.json', 'r') as f:
            agencies = json.load(f)
        return jsonify(agencies)
    except FileNotFoundError:
        return jsonify([])

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    if refresh_progress['status'] == 'running':
        return jsonify({'status': 'error', 'message': 'Refresh already in progress'}), 400
    
    # Reset progress
    refresh_progress['status'] = 'idle'
    refresh_progress['message'] = ''
    refresh_progress['start_time'] = None
    refresh_progress['end_time'] = None
    
    # Start refresh in a separate thread
    thread = threading.Thread(target=run_main_script)
    thread.start()
    
    return jsonify({'status': 'success', 'message': 'Refresh started'})

@app.route('/api/refresh/progress')
def get_refresh_progress():
    return jsonify({
        'status': refresh_progress['status'],
        'message': refresh_progress['message'],
        'start_time': refresh_progress['start_time'],
        'end_time': refresh_progress['end_time']
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    question = data.get('question', '')
    
    # Load the current agencies data
    with open('output.json', 'r') as f:
        agencies_data = json.load(f)
    
    # Construct the prompt with context
    context = f"Here is the current agencies data: {json.dumps(agencies_data)}"
    prompt = f"{context}\n\nQuestion: {question}\n\nPlease provide a detailed answer based on the data and use Google Search if needed for additional context. Format your response in HTML with proper paragraphs, lists, and styling. Use <p> for paragraphs, <ul> and <li> for lists, and <strong> for emphasis."
    
    # Prepare the Gemini call
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )
    ]
    
    tools = [types.Tool(google_search=types.GoogleSearch())]
    
    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        tools=tools,
        system_instruction=[types.Part.from_text(text="You are a helpful assistant analyzing letting agency data. Always format your responses in clean, well-structured HTML.")]
    )
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=generate_content_config
        )
        return jsonify({'answer': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True) 