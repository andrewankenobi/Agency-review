from flask import Flask, render_template, jsonify, request
import json
import subprocess
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

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
    try:
        # Run main.py in non-test mode
        subprocess.run(['python', 'main.py'], check=True)
        return jsonify({'status': 'success'})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True) 