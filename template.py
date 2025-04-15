import base64
import os
from google import genai
from google.genai import types


def generate():
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.5-pro-preview-03-25"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="""Execute the letting agency research as defined in the system prompt for the following entity:

* **Agency Name:** Fit Property Lettings Agent
* **Agency URL:** https://www.fitproperty.com/
"""),
            ],
        ),
        types.Content(
            role="model",
            parts=[
                types.Part.from_text(text="""The user wants me to research a UK letting agency called \"Fit Property Lettings Agent\" with the website \"https://www.fitproperty.com/\".

I need to follow the defined methodology:
1.  **Prioritize Google Search:** Use Google Search to find contact details, key personnel, property portals, branches, student listings, and bills policy.
2.  **Consult Agency Website:** Use the provided URL (https://www.fitproperty.com/) *only if necessary* to verify or find missing information.
3.  **Synthesize Findings:** Structure the information into the specified JSON format.

**Information Fields to Collect:**
*   Letting Agent: Fit Property Lettings Agent
*   Bills Included on Listings?: [Search]
*   Website Url: https://www.fitproperty.com/
*   Student Listings Live: [Search]
*   Key channels live on: [Search Rightmove, Zoopla, OnTheMarket, UniHomes]
*   Branches: [Search]
*   Key Contact Person (e.g., Director/Manager):
    *   Full Name: [Search]
    *   Position: [Search]
*   Contact Information:
    *   Phone: [Search]
    *   Address: [Search]
    *   Email: [Search]
*   LinkedIn: [Search for Key Contact Person's LinkedIn]
*   Other Linkedin/Extra Details: [Search for Company LinkedIn]
*   Notes/Comments: [Add notes if needed]

**Search Plan:**
1.  `Fit Property Lettings Agent contact details`
2.  `Fit Property Lettings Agent branches`
3.  `Fit Property Lettings Agent Director OR Manager`
4.  `Fit Property Lettings Agent site:rightmove.co.uk`
5.  `Fit Property Lettings Agent site:zoopla.co.uk`
6.  `Fit Property Lettings Agent site:onthemarket.com`
7.  `Fit Property Lettings Agent site:unihomes.co.uk`
8.  `Fit Property Lettings Agent student lettings`
9.  `Fit Property Lettings Agent \"bills included\"` (or check website if needed)
10. `[Key Contact Person Name] Fit Property Lettings Agent LinkedIn` (once name is found)
11. `Fit Property Lettings Agent LinkedIn` (for company page)

**Execution:**

*   **Search 1 & 2 (Contact/Branches):** Google Search for `Fit Property Lettings Agent contact details` and `Fit Property Lettings Agent branches`.
*   **Search 3 (Key Contact):** Google Search for `Fit Property Lettings Agent Director OR Manager`.
*   **Search 4-7 (Portals):** Google Search for `Fit Property Lettings Agent site:[portal_url]`.
*   **Search 8 (Student Listings):** Google Search for `Fit Property Lettings Agent student lettings`.
*   **Search 9 (Bills):** Google Search for `Fit Property Lettings Agent \"bills included\"`. If not found, check website.
*   **Search 10 (Contact LinkedIn):** Search once a name is identified.
*   **Search 11 (Company LinkedIn):** Search for the company page.

**Refinement based on initial searches:**
*   If Google Search doesn't yield specific contact names/emails/bills policy, I will browse the website (https://www.fitproperty.com/) specifically the 'Contact Us' and 'About Us' pages, and potentially look at sample listings for bills info.

Let's start the searches."""),
                types.Part.from_text(text="""```json
```json
{
  \"Letting Agent\": \"Fit Property Lettings Agent\",
  \"Bills Included on Listings?\": \"Some\",
  \"Website Url\": \"https://www.fitproperty.com/\",
  \"Student Listings Live\": \"Yes\",
  \"Key channels live on\": [
    \"Rightmove\",
    \"Zoopla\",
    \"UniHomes\"
  ],
  \"Branches\": \"1\",
  \"Key Contact Person (e.g., Director/Manager)\": {
    \"Full Name\": \"Adam Lee\",
    \"Position\": \"Director\"
  },
  \"Contact Information\": {
    \"Phone\": \"01142 725773\",
    \"Address\": \"144 Charles Street, Sheffield S1 2NE\",
    \"Email\": \"hello@fitproperty.com\"
  },
  \"LinkedIn\": \"Not Found\",
  \"Other Linkedin/Extra Details\": \"Not Found\",
  \"Notes/Comments\": \"The agency focuses on Sheffield student and residential lettings. Their website mentions 'Bills Managed' as a service, and Rightmove listings show some properties with 'Bills Included' or 'Bills inclusive package available'. Google Search identified Adam Lee as a Director associated with Fit Property and StudentTenant.co.uk. Another search result mentioned Joel Walker was previously Head of Property Management at Fit Property but has since moved on. No specific LinkedIn profiles for key personnel or the company were readily found via Google Search.\"
}
```"""),
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="""INSERT_INPUT_HERE"""),
            ],
        ),
    ]
    tools = [
        types.Tool(google_search=types.GoogleSearch())
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        tools=tools,
        response_mime_type="text/plain",
        system_instruction=[
            types.Part.from_text(text="""You are an AI assistant specialized in researching UK letting agencies based on publicly available online information. Your task is to extract key details about a specific letting agency, whose name and website URL will be provided in the user prompt.

**Core Objective:**
Collect and structure information about the specified letting agency according to the fields listed below.

**Methodology:**
1.  **Prioritize Google Search:** Use Google Search as the primary tool to find information about the agency's online presence, contact details, key personnel, and the property portals they use.
2.  **Consult Agency Website:** Browse the provided agency website URL *only if necessary* to:
    * Verify information found via search (e.g., specific contact details).
    * Find information not readily available in search results (e.g., 'Bills Included' policy, specific staff names/roles from an 'About Us' page).
3.  **Synthesize Findings:** Consolidate the information gathered into the specified output format.

**Information Fields to Collect:**

For the agency specified in the user prompt, find and report the following details. If a specific piece of information cannot be reliably found using Google Search and Browse the agency site, clearly state 'Not Found' for that field.

* **Letting Agent:** [The Agency Name provided in the user prompt]
* **Bills Included on Listings?:** [Search the agency website/Google Search results for mentions of bills/utilities policy. State: Yes, No, Some, or Not Found]
* **Website Url:** [The Agency URL provided in the user prompt]
* **Student Listings Live:** [Use Google Search for '[Agency Name] student lettings' or similar, and check the agency website. Provide a count if easily found, otherwise state 'Yes' if student listings exist but count is unavailable, or 'Not Found']
* **Key channels live on:** [Perform Google Searches for `[Agency Name] site:rightmove.co.uk`, `[Agency Name] site:zoopla.co.uk`, `[Agency Name] site:onthemarket.com`, `[Agency Name] site:unihomes.co.uk`. List the names of the portals where they are found (e.g., Rightmove, Zoopla, OnTheMarket, UniHomes).]
* **Branches:** [Search Google for '[Agency Name] branches' or office locations. State the number found (e.g., '1', '2+'). State 'Not Found' otherwise.]
* **Key Contact Person (e.g., Director/Manager):**
    * **Full Name:** [Search Google for '[Agency Name] Director', '[Agency Name] Manager', or check website 'About Us'/'Contact' page. Identify a senior contact.]
    * **Position:** [State the job title of the person identified.]
* **Contact Information:**
    * **Phone:** [Search Google for '[Agency Name] phone number' or check website contact page.]
    * **Address:** [Search Google for '[Agency Name] address' or check website contact page.]
    * **Email:** [Search Google for '[Agency Name] email' or '[Key Contact Person Name] email'. Check website contact page. Provide general contact email if specific one isn't found.]
* **LinkedIn:** [Search Google for '[Key Contact Person Name] [Agency Name] LinkedIn'. Provide the full LinkedIn profile URL if found.]
* **Other Linkedin/Extra Details:** [Note relevant company LinkedIn page URL or other pertinent details discovered.]
* **Notes/Comments:** [Include brief notes on difficulties, ambiguities, or key observations relevant to the data collection.]

**Output:**
Present the collected information clearly, adhering strictly to the field names listed above. Return valid JSON
"""),
        ],
    )

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        print(chunk.text, end="")

if __name__ == "__main__":
    generate()
