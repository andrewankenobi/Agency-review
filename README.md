# UK Letting Agency Research Tool

This Python application automates the research of UK letting agencies using the Gemini API with Google Search grounding. It processes a list of agencies, gathers information about them, and stores the results in a structured format.

## Features

- Automated research of UK letting agencies
- Integration with Google's Gemini API
- Google Search grounding for accurate information
- Structured JSON output
- Modern web interface for viewing results
- Real-time progress tracking and logging
- System prompt management
- Robust error handling and recovery
- Concurrent request prevention
- Thread-safe operations

## Prerequisites

- Python 3.9 or higher
- Google Gemini API key
- Required Python packages (listed in requirements.txt)

## Project Structure

```
.
├── main.py              # Main application script
├── app.py              # Web interface application
├── agencies.json       # Input file containing agency data
├── system_prompt.txt   # Gemini system prompt
├── default_system_prompt.txt  # Default system prompt
├── output.json         # Generated research results
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (API key)
└── templates/         # Web interface templates
    └── index.html    # Main web interface template
```

## Setup Instructions

1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd [repository-name]
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create necessary configuration files:

   a. Create `.env` file in the project root:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

   b. Ensure `agencies.json` exists with the following structure:
   ```json
   [
     {
       "name": "Agency Name",
       "url": "https://agency-website.com"
     }
   ]
   ```

   c. Ensure `system_prompt.txt` exists with the Gemini system prompt

## Running the Application

1. Start the web interface:
   ```bash
   python app.py
   ```
   Then open your browser to `http://localhost:5001`

2. The web interface provides:
   - Agency data viewing
   - Search functionality
   - Data refresh capability
   - System prompt management
   - Real-time progress tracking

## Web Interface Features

- **Agency Search**: Filter agencies by name, address, contact details
- **Data Refresh**: Trigger and monitor data refresh operations
- **Progress Tracking**: Real-time progress updates with detailed logging
- **System Prompt Management**: Edit and revert system prompts
- **Raw Data Viewing**: Access to source data for each agency
- **Responsive Design**: Works on desktop and mobile devices

## Error Handling

The application includes robust error handling for:
- Missing or invalid API keys
- Network issues and connection errors
- Invalid JSON responses
- File I/O errors
- Concurrent request prevention
- Thread safety and resource management

All errors are logged and displayed in the web interface for easy debugging.

## Security Features

- API keys stored in environment variables
- Thread-safe operations
- Input validation
- Error message sanitization
- Concurrent request prevention

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Specify your license here]

## Support

For support, please [provide contact information or issue reporting guidelines] 