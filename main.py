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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agency_research.log', mode='w'),  # 'w' mode overwrites the file
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add a startup message to indicate new run
logger.info("Starting agency research application")
logger.info("Log file cleared for new run")


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
    """Construct the user prompt for a specific agency."""
    prompt = f"""Execute the letting agency research as defined in the system prompt for the following entity:

* **Agency Name:** {agency_name}
* **Agency URL:** {agency_url}
"""
    logger.debug(f"Constructed prompt for {agency_name}")
    return prompt


def clean_response_text(text: str) -> str:
    """Clean up the response text by removing reference numbers and other artifacts."""
    # Remove reference numbers like [12], [21], etc.
    text = re.sub(r'\[\d+\]', '', text)
    # Remove any remaining square brackets
    text = re.sub(r'\[|\]', '', text)
    return text


def clean_markdown_text(text: str) -> str:
    """Clean up markdown formatting while preserving all content."""
    # Remove markdown bold markers
    text = text.replace('**', '')
    # Remove markdown list markers but preserve the content
    text = text.replace('*   ', '')
    # Replace *or* with a comma for better readability
    text = text.replace('*or*', ',')
    # Remove extra whitespace but preserve newlines
    text = '\n'.join(line.strip() for line in text.split('\n'))
    return text.strip()


def ensure_text_completeness(text: str) -> str:
    """Ensure text fields are complete and not truncated."""
    # Check for common truncation patterns
    if text.endswith('...') or text.endswith('...]') or text.endswith('...)'):
        logger.warning(f"Detected potentially truncated text: {text}")
    return text


def process_agency(
    agency: Dict[str, str],
    system_prompt: str,
    client: genai.Client,
    max_retries: int = 3
) -> Dict[str, Any]:
    """Process a single agency using the Gemini API."""
    logger.info(f"Starting processing for agency: {agency['name']}")
    user_prompt = construct_user_prompt(agency["name"], agency["url"])
    
    # Prepare the Gemini call
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_prompt)
            ]
        )
    ]
    
    tools = [types.Tool(google_search=types.GoogleSearch())]
    
    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        tools=tools,
        response_mime_type="text/plain",
        system_instruction=[types.Part.from_text(text=system_prompt)]
    )
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"Sending API request for {agency['name']} (attempt {attempt + 1}/{max_retries})")
            response = client.models.generate_content_stream(
                model="gemini-2.5-pro-preview-03-25",
                contents=contents,
                config=generate_content_config
            )
            
            # Collect the response text
            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    logger.debug(f"Received chunk for {agency['name']}: {chunk.text[:100]}...")
            
            # Log the full response for debugging
            logger.info(f"Full response for {agency['name']}:\n{full_response}")
            
            # Check if response is empty or malformed
            if not full_response or not full_response.strip():
                logger.warning(f"Empty response received for {agency['name']} on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise ValueError("Empty response after all retries")
            
            # Convert markdown response to JSON
            try:
                # Initialize result dictionary with basic info
                result = {
                    "Letting Agent": agency["name"],
                    "Website Url": agency["url"]
                }
                
                # Split response into lines and process each line
                lines = full_response.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('*   **'):
                        # Extract key and value from markdown format
                        key_value = line[6:-2].split(':**')  # Remove '*   **' and '**'
                        if len(key_value) == 2:
                            key = key_value[0].strip()
                            value = key_value[1].strip()
                            
                            # Clean up the key to match expected format
                            key = key.replace(' ', '_').lower()
                            
                            # Handle special cases
                            if key == 'bills_included_on_listings?':
                                key = 'bills_included'
                                value = value.lower() in ['yes', 'some']
                            elif key == 'student_listings_live':
                                key = 'student_listings'
                                value = value.lower() == 'yes'
                            elif key == 'key_channels_live_on':
                                key = 'channels'
                                # Split by comma and preserve reference numbers
                                value = [channel.strip() for channel in value.split(',')]
                                # Remove any empty strings
                                value = [v for v in value if v]
                            else:
                                # Clean up markdown formatting while preserving content
                                value = clean_markdown_text(value)
                                # Ensure text completeness
                                value = ensure_text_completeness(value)
                            
                            result[key] = value
                
                # Validate required fields
                required_fields = ['bills_included', 'student_listings', 'channels']
                missing_fields = [field for field in required_fields if field not in result]
                
                if missing_fields:
                    logger.warning(f"Missing required fields for {agency['name']}: {', '.join(missing_fields)}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying due to missing required fields...")
                        continue
                    else:
                        # Set default values for missing fields
                        for field in missing_fields:
                            result[field] = None
                
                logger.info(f"Successfully processed {agency['name']}")
                return result
                
            except Exception as e:
                logger.error(f"Error converting response to JSON for {agency['name']}: {str(e)}")
                logger.error(f"Raw response that caused error: {full_response}")
                if attempt < max_retries - 1:
                    continue
                else:
                    return {
                        "Letting Agent": agency["name"],
                        "Website Url": agency["url"],
                        "Error": f"Error converting response to JSON: {str(e)}",
                        "Raw Response": full_response[:500]
                    }
            
        except Exception as e:
            logger.error(f"Error processing agency {agency['name']}: {str(e)}", exc_info=True)
            if attempt < max_retries - 1:
                continue
            else:
                return {
                    "Letting Agent": agency["name"],
                    "Website Url": agency["url"],
                    "Error": str(e)
                }
    
    # If we get here, all retries failed
    return {
        "Letting Agent": agency["name"],
        "Website Url": agency["url"],
        "Error": "All retry attempts failed"
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
    """Process a batch of agencies in parallel."""
    logger.info(f"Starting batch processing for {len(agencies)} agencies")
    batch_results = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        future_to_agency = {
            executor.submit(process_agency, agency, system_prompt, client): agency
            for agency in agencies
        }
        
        # Process results as they complete
        for future in as_completed(future_to_agency):
            agency = future_to_agency[future]
            try:
                result = future.result()
                batch_results.append(result)
                logger.info(f"Completed processing: {agency['name']}")
            except Exception as e:
                logger.error(f"Error processing agency {agency['name']}: {str(e)}", exc_info=True)
                batch_results.append({
                    "Letting Agent": agency["name"],
                    "Website Url": agency["url"],
                    "Error": str(e)
                })
    
    logger.info(f"Completed batch processing with {len(batch_results)} results")
    return batch_results


def main(test_mode: bool = False) -> None:
    try:
        logger.info("Starting agency research application")
        if test_mode:
            logger.info("Running in TEST MODE - will only process first 5 agencies")
        
        # Load configuration
        api_key = load_environment_variables()
        all_agencies = load_agencies()
        system_prompt = load_system_prompt()
        
        # Initialize Gemini
        client = initialize_gemini_client(api_key)
        
        # Process agencies in batches of 5
        batch_size = 5
        all_results = []
        
        # In test mode, only process first 5 agencies
        if test_mode:
            all_agencies = all_agencies[:5]
            logger.info(f"Test mode: Processing only {len(all_agencies)} agencies")
        
        for i in range(0, len(all_agencies), batch_size):
            batch = all_agencies[i:i + batch_size]
            logger.info(f"\nProcessing batch {i//batch_size + 1} of {(len(all_agencies) + batch_size - 1)//batch_size}")
            logger.info(f"Agencies in this batch: {', '.join(agency['name'] for agency in batch)}")
            
            batch_results = process_agency_batch(batch, system_prompt, client)
            all_results.extend(batch_results)
            
            # Save results after each batch
            save_results(all_results)
            logger.info(f"Saved results after batch {i//batch_size + 1}")
            
            # Add a small delay between batches to avoid rate limiting
            if i + batch_size < len(all_agencies):
                logger.info("Waiting 10 seconds before next batch...")
                time.sleep(10)
        
        logger.info("\nProcessing complete. All results saved to output.json")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process letting agencies data.')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode (process only first 5 agencies)')
    args = parser.parse_args()
    
    # Run main with test mode flag
    main(test_mode=args.test_mode) 