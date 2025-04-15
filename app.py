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

def run_main_script():
    """Run the main.py script to refresh the data."""
    try:
        # Get the absolute path to main.py
        main_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
        
        # Check if main.py exists
        if not os.path.exists(main_script_path):
            logger.error(f"main.py not found at {main_script_path}")
            refresh_progress['status'] = 'error'
            refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Error: main.py not found'
            save_progress()
            return
            
        # Set initial status
        refresh_progress['status'] = 'running'
        refresh_progress['start_time'] = time.time()
        refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Starting data refresh...'
        save_progress()
        
        # Run main.py with unbuffered output and proper stream handling
        process = subprocess.Popen(
            ['python3', '-u', main_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read both stdout and stderr in real-time
        while True:
            # Read stdout
            output = process.stdout.readline()
            if output:
                message = output.strip()
                if message:
                    # Check if this is a log message
                    if message.startswith("20"):  # Log messages start with timestamp
                        # Extract the actual message part
                        actual_message = " ".join(message.split(" - ")[2:])
                        timestamped_message = f'[{time.strftime("%I:%M:%S %p")}] {actual_message}'
                    else:
                        timestamped_message = f'[{time.strftime("%I:%M:%S %p")}] {message}'
                    
                    refresh_progress['message'] = timestamped_message
                    logger.info(f"Progress update: {message}")
                    save_progress()
            
            # Read stderr
            error = process.stderr.readline()
            if error:
                error_message = error.strip()
                if error_message:
                    # Only treat as error if it's not a log message
                    if not error_message.startswith("20"):
                        logger.error(f"Script error: {error_message}")
                        refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Error: {error_message}'
                        save_progress()
            
            # Check if process has finished
            if process.poll() is not None:
                break
        
        # Get any remaining output
        stdout, stderr = process.communicate()
        
        # Log any remaining output
        if stdout:
            for line in stdout.splitlines():
                if line.strip():
                    logger.info(f"Remaining stdout: {line}")
        if stderr:
            for line in stderr.splitlines():
                if line.strip() and not line.startswith("20"):  # Skip log messages
                    logger.error(f"Remaining stderr: {line}")
        
        # Check process return code
        if process.returncode != 0:
            refresh_progress['status'] = 'error'
            error_msg = stderr if stderr else "Unknown error occurred"
            refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Error: {error_msg}'
            logger.error(f"Process failed with error: {error_msg}")
        else:
            refresh_progress['status'] = 'complete'
            refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Data refresh completed successfully'
            logger.info("Process completed successfully")
        
        refresh_progress['end_time'] = time.time()
        save_progress()
        
    except Exception as e:
        refresh_progress['status'] = 'error'
        refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Error: {str(e)}'
        refresh_progress['end_time'] = time.time()
        save_progress()
        logger.error(f"Error in run_main_script: {str(e)}", exc_info=True)

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

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    logger.info("Received refresh request")
    logger.info(f"Current status: {refresh_progress['status']}")
    
    if refresh_progress['status'] == 'running':
        logger.warning("Refresh already in progress - attempting to reset state")
        try:
            cleanup_progress()
        except Exception as e:
            logger.error(f"Failed to reset progress state: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Failed to reset refresh state'}), 500
    
    try:
        # Reset progress
        refresh_progress['status'] = 'idle'
        refresh_progress['message'] = ''
        refresh_progress['start_time'] = None
        refresh_progress['end_time'] = None
        save_progress()
        
        logger.info("Starting refresh process")
        
        # Start refresh in a separate thread
        thread = threading.Thread(target=run_main_script)
        thread.daemon = True  # Make thread daemon so it doesn't prevent app shutdown
        thread.start()
        
        # Set initial running state
        refresh_progress['status'] = 'running'
        refresh_progress['start_time'] = time.time()
        refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Starting data refresh...'
        save_progress()
        
        logger.info("Refresh process started successfully")
        return jsonify({'status': 'success', 'message': 'Refresh started'})
    except Exception as e:
        logger.error(f"Error starting refresh: {str(e)}", exc_info=True)
        refresh_progress['status'] = 'error'
        refresh_progress['message'] = f'[{time.strftime("%I:%M:%S %p")}] Error: {str(e)}'
        refresh_progress['end_time'] = time.time()
        save_progress()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/refresh/progress')
def get_refresh_progress():
    logger.debug(f"Progress check: {refresh_progress['status']} - {refresh_progress['message']}")
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
    try:
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output.json')
        with open(output_path, 'r', encoding='utf-8') as f:
            agencies_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading agencies data: {str(e)}")
        return jsonify({'error': 'Failed to load agencies data'}), 500
    
    # Format the agencies data for display
    formatted_agencies = []
    for agency in agencies_data:
        formatted_agency = {
            'name': agency.get('Letting Agent', 'N/A'),
            'url': agency.get('Website Url', 'N/A'),
            'address': agency.get('contact_info', {}).get('address', 'N/A'),
            'phone': agency.get('contact_info', {}).get('phone', 'N/A'),
            'contact_person': agency.get('key_contact', {}).get('full_name', 'N/A'),
            'position': agency.get('key_contact', {}).get('position', 'N/A'),
            'email': agency.get('contact_info', {}).get('email', 'N/A'),
            'branches': agency.get('Branches', 'N/A'),
            'bills_included': agency.get('bills_included', 'N/A'),
            'student_listings': agency.get('student_listings', 'N/A'),
            'channels': ', '.join(agency.get('channels', ['N/A'])),
            'linkedin': agency.get('linkedin', 'N/A'),
            'notes': agency.get('notes', 'N/A'),
            'search_queries': agency.get('Search Queries', [])
        }
        formatted_agencies.append(formatted_agency)
    
    # Construct the prompt with formatted context
    context = f"Here is the current agencies data: {json.dumps(formatted_agencies, indent=2)}"
    prompt = f"""Hello! I'd love to help you explore the letting agency data. 

Your question: {question}

I have access to detailed information about various letting agencies, including their services, locations, and features. I can help you:
- Compare different agencies
- Find specific information about services or locations
- Analyze trends and patterns
- Answer any questions about the letting agency landscape

Let me know what interests you, and I'll do my best to provide helpful insights!"""
    
    # Prepare the Gemini call
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )
    ]
    
    tools = [types.Tool(google_search=types.GoogleSearch())]
    
    generate_content_config = types.GenerateContentConfig(
        temperature=0.7,
        tools=tools,
        system_instruction=[types.Part.from_text(text="""You are a friendly and enthusiastic assistant helping users explore letting agency data. Your role is to:

1. Be warm, welcoming, and helpful in your tone
2. Use a conversational but professional style
3. Format all responses in valid HTML with proper styling
4. When users ask vague questions, gently guide them with friendly suggestions
5. Structure information clearly with HTML tags:
   - Use <p> for paragraphs
   - Use <ul> and <li> for lists
   - Use <strong> for emphasis
   - Use <h3> for section headers
   - Use <div class="info-box"> for important notes
6. Always maintain a positive and helpful attitude
7. If a question is unclear, offer friendly suggestions for what information you can provide

Example response format:
<div class="response">
    <h3>Welcome!</h3>
    <p>I'd be happy to help you explore the letting agency data. Here are some interesting things we could look at:</p>
    <ul>
        <li>Comparing different agencies' services</li>
        <li>Finding agencies in specific locations</li>
        <li>Analyzing trends in the market</li>
    </ul>
    <p>What would you like to know more about?</p>
</div>""")]
    )
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=generate_content_config
        )
        return jsonify({'answer': response.text})
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
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
    app.run(debug=True, port=5001) 