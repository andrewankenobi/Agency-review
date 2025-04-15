import os
import json
import time
import logging
import argparse
import re
from typing import List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types
from dotenv import load_dotenv

# Custom filter to exclude AFC messages
class ExcludeAFCFilter(logging.Filter):
    def filter(self, record):
        return not ('AFC' in record.getMessage() or 'remote call' in record.getMessage())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agency_research.log', mode='w'),  # 'w' mode overwrites the file
        logging.StreamHandler()  # This will print to console
    ]
)
logger = logging.getLogger(__name__)
# Add filter to exclude AFC messages
logger.addFilter(ExcludeAFCFilter())

# Add a startup message to indicate new run
logger.info("Starting agency research application")
logger.info("Log file cleared for new run")
print("Starting agency research application...", flush=True)  # Force immediate console output


def load_environment_variables() -> str:
    """Load environment variables and return the Gemini API key."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    logger.info("Successfully loaded environment variables")
    return api_key


def load_agencies(file_path: str = "agencies.json") -> List[Dict[str, str]]:
    """Load the list of agencies from the JSON file."""
    try:
        with open(file_path, "r") as f:
            agencies = json.load(f)
            logger.info(f"Successfully loaded {len(agencies)} agencies from {file_path}")
            return agencies
    except FileNotFoundError:
        raise FileNotFoundError(f"Agencies file not found: {file_path}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in {file_path}")


def load_system_prompt(file_path: str = "system_prompt.txt") -> str:
    """Load the system prompt from the text file."""
    try:
        with open(file_path, "r") as f:
            prompt = f.read().strip()
            logger.info(f"Successfully loaded system prompt from {file_path}")
            return prompt
    except FileNotFoundError:
        raise FileNotFoundError(f"System prompt file not found: {file_path}")


def initialize_gemini_client(api_key: str) -> genai.Client:
    """Initialize the Gemini client with the API key."""
    client = genai.Client(api_key=api_key)
    logger.info("Successfully initialized Gemini client")
    return client


def construct_user_prompt(agency_name: str, agency_url: str) -> str:
    """Construct a simple user prompt for a specific agency."""
    prompt = f"""Please research the following letting agency:

* Name: {agency_name}
* Website: {agency_url}

Follow the instructions in the system prompt to find and format the required information."""
    logger.debug(f"Constructed simplified prompt for {agency_name}")
    return prompt


def save_raw_response(agency_name: str, response_text: str, raw_dir: str) -> str:
    """Save the raw response text to a file with a consistent filename format."""
    # Clean the agency name to create a consistent filename
    filename = agency_name.lower()
    
    # Replace special characters and spaces with underscores
    filename = re.sub(r'[^a-z0-9]', '_', filename)
    
    # Remove multiple consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    
    # Add suffix
    filename = f"{filename}_response.txt"
    
    # Create directory if it doesn't exist
    os.makedirs(raw_dir, exist_ok=True)
    
    file_path = os.path.join(raw_dir, filename)
    
    with open(file_path, "w", encoding='utf-8') as f:
        f.write(response_text)
    
    return file_path


def process_raw_response(client: genai.Client, file_path: str) -> Dict[str, Any]:
    """Process a raw response file into structured JSON using Gemini.
       Extracts only the main response part, ignoring metadata."""
    with open(file_path, "r", encoding='utf-8') as f:
        full_content = f.read()

    # Extract only the main response part before any metadata separators
    raw_response_text = full_content.split("---")[0].strip()
    if "RESPONSE:" in raw_response_text:
        raw_response_text = raw_response_text.split("RESPONSE:")[1].strip()
    if "METADATA:" in raw_response_text:
        raw_response_text = raw_response_text.split("METADATA:")[0].strip()

    # Initialize structured_data with default values
    structured_data = {
        "Letting Agent": "Not Found in Text",
        "Website Url": "Not Found in Text",
        "bills_included": "Not Found",
        "student_listings": "Not Found",
        "channels": [],
        "Branches": "Not Found",
        "key_contact": {"full_name": "Not Found", "position": "Not Found"},
        "contact_info": {"phone": "Not Found", "address": "Not Found", "email": "Not Found"},
        "linkedin": "Not Found",
        "other_linkedin": "Not Found",
        "notes": ""
    }

    # Construct prompt for structuring the data
    structure_prompt = """Please analyze the following research text and convert it into a structured JSON format.
The data should follow this exact structure:

{
    "Letting Agent": "Agency Name",
    "Website Url": "URL",
    "bills_included": "Yes/No/Some/Not Found",
    "student_listings": "Yes/No/Not Found",
    "channels": ["Rightmove", "Zoopla", "OnTheMarket", "UniHomes"],
    "Branches": "Number or Not Found",
    "key_contact": {
        "full_name": "Name or Not Found",
        "position": "Position or Not Found"
    },
    "contact_info": {
        "phone": "Phone or Not Found",
        "address": "Address or Not Found",
        "email": "Email or Not Found"
    },
    "linkedin": "URL or Not Found",
    "other_linkedin": "URL or Not Found",
    "notes": "Any additional notes or observations based *only* on the provided text"
}

Important:
1. Base the JSON *strictly* on the provided research text. Do not infer or add outside information.
2. Use "Not Found" for any information that cannot be reliably determined *from the text*.
3. For bills_included, use "Yes", "No", "Some", or "Not Found".
4. For student_listings, use "Yes", "No", or "Not Found".
5. For channels, only include portals explicitly mentioned *in the text*.
6. For Branches, use the number found or "Not Found".
7. Extract the agency name and URL from the text if possible, otherwise use placeholders.

Research text to analyze:
"""

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=structure_prompt + raw_response_text)
            ]
        )
    ]

    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro-preview-03-25", # Using flash for speed/cost in structuring
            contents=contents,
            config=generate_content_config
        )

        # Parse the JSON response
        try:
            parsed_data = json.loads(response.text)
            # Update structured_data with parsed values, maintaining defaults for missing fields
            for key, value in parsed_data.items():
                if key in structured_data:
                    if isinstance(value, dict) and isinstance(structured_data[key], dict):
                        structured_data[key].update(value)
                    else:
                        structured_data[key] = value
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response for {file_path}")
            # Keep the default structured_data

        # Add reference to the raw file for traceability
        structured_data["RawDataSourceFile"] = os.path.basename(file_path)

        return structured_data

    except Exception as e:
        logger.error(f"Error processing raw response {file_path}: {str(e)}", exc_info=True)
        return {
            "Error": f"Error processing raw response: {str(e)}",
            "Raw File": os.path.basename(file_path)
        }


def process_agency(
    agency: Dict[str, str],
    system_prompt: str,
    client: genai.Client,
    max_retries: int = 3
) -> Dict[str, Any]:
    """Process a single agency using the Gemini API with grounding."""
    logger.info(f"Starting processing for agency: {agency['name']}")
    user_prompt = construct_user_prompt(agency["name"], agency["url"])

    # Prepare the Gemini call with proper search tool configuration
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_prompt)
            ]
        )
    ]

    # Configure the Google Search tool
    google_search_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    # Configure tool use mode
    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        tools=[google_search_tool],
        response_mime_type="text/plain",
        system_instruction=[types.Part.from_text(text=system_prompt)]
    )

    # Initialize variables for the successful response
    successful_response = None
    successful_file_path = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.warning(f"Retry attempt {attempt + 1} for {agency['name']}")
                print(f"Retry attempt {attempt + 1} for {agency['name']}", flush=True)
                time.sleep(5 * attempt) # Exponential backoff for retries

            logger.debug(f"Sending API request for {agency['name']} (attempt {attempt + 1}/{max_retries})")
            response = client.models.generate_content(
                model="gemini-2.5-pro-preview-03-25",
                contents=contents,
                config=generate_content_config
            )

            # Check if response is None or has no text
            if response is None:
                raise ValueError("No response received from Gemini API")
            if not hasattr(response, 'text'):
                raise ValueError("Response object has no text attribute")
            if response.text is None:
                raise ValueError("Response text is None")
            if not response.text.strip():
                raise ValueError("Response text is empty")

            # Extract the response text and clean it
            response_text = response.text.strip()
            
            # Remove any metadata sections if they exist
            if "---" in response_text:
                response_text = response_text.split("---")[0].strip()
            if "METADATA:" in response_text:
                response_text = response_text.split("METADATA:")[0].strip()
            if "RESPONSE:" in response_text:
                response_text = response_text.split("RESPONSE:")[1].strip()

            # Store the successful response
            successful_response = response_text
            break  # Exit the retry loop on success

        except Exception as e:
            error_msg = f"Error processing agency {agency['name']} on attempt {attempt + 1}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if attempt < max_retries - 1:
                continue
            else:
                return {
                    "Letting Agent": agency["name"],
                    "Website Url": agency["url"],
                    "Error": f"Failed after {max_retries} attempts. Last error: {str(e)}",
                    "RawDataSourceFile": None
                }

    # If we have a successful response, save it and process it
    if successful_response is not None:
        # Save the cleaned response
        successful_file_path = save_raw_response(agency["name"], successful_response, "raw")
        logger.debug(f"Saved response to: {successful_file_path}")

        # Process the raw response into structured JSON
        structured_data = process_raw_response(client, successful_file_path)
        
        # Ensure the agency name is correctly set in the structured data
        structured_data["Letting Agent"] = agency["name"]
        structured_data["Website Url"] = agency["url"]
        structured_data["RawDataSourceFile"] = os.path.basename(successful_file_path)

        logger.info(f"Successfully processed {agency['name']}")
        return structured_data

    return {
        "Letting Agent": agency["name"],
        "Website Url": agency["url"],
        "Error": "All retry attempts failed unexpectedly.",
        "RawDataSourceFile": None
    }


def save_results(results: List[Dict[str, Any]], file_path: str = "output.json") -> None:
    """Save the results to a JSON file."""
    try:
        # Only create directory if file_path contains a directory
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        # Save with better handling of long strings
        with open(file_path, "w", encoding='utf-8') as f:
            json.dump(
                results, 
                f, 
                indent=2,
                ensure_ascii=False,  # Preserve non-ASCII characters
                default=str  # Handle any non-serializable objects
            )
        
        # Verify the saved file
        with open(file_path, "r", encoding='utf-8') as f:
            loaded_data = json.load(f)
            if len(loaded_data) != len(results):
                logger.error(f"Data loss detected! Saved {len(loaded_data)} items but expected {len(results)}")
            
        logger.info(f"Saved {len(results)} results to {file_path}")
    except Exception as e:
        logger.error(f"Error saving results to {file_path}: {str(e)}")
        raise


def process_agency_batch(
    agencies: List[Dict[str, str]],
    system_prompt: str,
    client: genai.Client
) -> List[Dict[str, Any]]:
    """Process a batch of agencies using ThreadPoolExecutor with rate limiting."""
    results = []
    total_agencies = len(agencies)
    
    logger.info(f"Starting batch processing for {total_agencies} agencies...")
    print(f"Starting research for {total_agencies} agencies...", flush=True)
    
    # Use max_workers=5 for parallel processing to avoid hitting rate limits
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks and store futures
        future_to_agency = {
            executor.submit(process_agency, agency, system_prompt, client): agency
            for agency in agencies
        }
        
        # Process completed futures as they complete
        completed = 0
        for future in as_completed(future_to_agency):
            completed += 1
            agency = future_to_agency[future]
            try:
                result = future.result()
                results.append(result)
                progress = (completed/total_agencies)*100
                logger.info(f"Completed {agency['name']} ({completed}/{total_agencies}, {progress:.1f}%)")
                print(f"Completed {agency['name']} ({completed}/{total_agencies}, {progress:.1f}%)", flush=True)
            except Exception as e:
                error_msg = str(e)
                if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                    logger.error(f"Quota exceeded for {agency['name']}. Please wait and try again later.")
                    print(f"Quota exceeded for {agency['name']}. Please wait and try again later.", flush=True)
                    # Add a failed result with quota error
                    results.append({
                        "Letting Agent": agency["name"],
                        "Website Url": agency["url"],
                        "Error": "Quota exceeded. Please try again later.",
                        "RawDataSourceFile": None
                    })
                else:
                    logger.error(f"Error processing {agency['name']}: {str(e)}")
                    print(f"Error processing {agency['name']}: {str(e)}", flush=True)
                    results.append({
                        "Letting Agent": agency["name"],
                        "Website Url": agency["url"],
                        "Error": str(e),
                        "RawDataSourceFile": None
                    })
    
    logger.info(f"Batch processing completed for all {total_agencies} agencies")
    print(f"Research completed for all {total_agencies} agencies", flush=True)
    return results


if __name__ == "__main__":
    try:
        # Load environment variables
        api_key = load_environment_variables()
        
        # Initialize Gemini client
        client = initialize_gemini_client(api_key)
        
        # Load system prompt
        system_prompt = load_system_prompt()
        
        # Load agencies
        agencies = load_agencies()
        
        # Process agencies
        results = process_agency_batch(agencies, system_prompt, client)
        
        # Save results
        save_results(results)
        
        print("All agencies processed successfully!", flush=True)
    except Exception as e:
        print(f"Error in main execution: {str(e)}", flush=True)
        raise