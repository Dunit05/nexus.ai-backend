import cohere
import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import json
import requests

# Load environment variables
load_dotenv()
coherekey = os.getenv("COHERE_API_KEY")
if not coherekey:
    raise ValueError("COHERE_API_KEY not found in environment variables")

# Initialize Cohere client
co = cohere.ClientV2(api_key=coherekey)

# Initialize Firestore
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize FastAPI app
app = FastAPI()

# we need this so that the api is able to work with different origins/frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def prioritize_task(user_input: str) -> str:
    try:
        res = co.chat(
            model="command-r7b-12-2024",
            messages=[
                {
                    "role": "user",
                    "content": f"Prioritize this task using High, Medium, or Low urgency: {user_input}. Do not reply with anything else.",
                }
            ],
        )
        return res.message.content[0].text
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Function to summarize text using Cohere
def summarizebot(user_input: str) -> str:
    try:
        res = co.chat(
            model="command-r7b-12-2024",
            messages=[
                {
                    "role": "user",
                    "content": f"I want to summarize the following text in less than 3 sentences: {user_input}. If you don't know how to respond, just say 'I don't know'.",
                }
            ],
        )
        return res.message.content[0].text
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def checkAvailability1(user_input: str):
    try:
        res = co.chat(
            model="command-r7b-12-2024",
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    Extract the details from this scheduling request and return them as a JSON object with the following fields:
                    {{
                        "task_name": "<Task Name>",
                        "duration_hours": <Duration in hours (positive number)>,
                        "week_start": "<YYYY-MM-DD>",
                        "week_end": "<YYYY-MM-DD>"
                    }}

                    Only return the JSON object. Do not include explanations, formatting, or any extra text.
                    If you are unable to extract the details, return an empty JSON object: {{}}.

                    Text: {user_input}
                    """
                }
            ],
        )

        print("AI Response:", res.message.content)

        response_text = res.message.content[0].text if res.message.content else ""
        response_text = response_text.strip("```json").strip("```").strip()

        if not response_text:
            raise HTTPException(status_code=500, detail="AI response is empty.")

        try:
            event_data = json.loads(response_text)
            if not event_data.get("task_name") or not event_data.get("duration_hours"):
                raise ValueError("Missing required fields in AI response.")

            print("Extracted Event Data:", event_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=500, detail=f"Invalid JSON response: {response_text}")

        # Call Logic Apps API
        logic_apps_url = "https://prod-21.northcentralus.logic.azure.com:443/workflows/e1d025b460494c53862f958fe67c0be9/triggers/When_a_HTTP_request_is_received/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=3FElBEyk25j3s6YLw3L2nw45EjCugN7May7ixC6NUWc"
        response = requests.post(logic_apps_url, json=event_data)

        try:
            available_dates = response.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Invalid response from Logic Apps API")

        print("Unavailable Times:", json.dumps(available_dates, indent=2))

        request = f"""
        I want to schedule the following event:
        {json.dumps(event_data, indent=2)}

        Please note that I am **unavailable** during the following times:
        {json.dumps(available_dates, indent=2)}

        Based on this, provide a list of available time slots that fit my schedule.
        """

        return provideDates(request)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def provideDates(user_input: str):
    try:
        res = co.chat(
            model="command-r7b-12-2024",
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    Based on the following unavailable times, determine **only the available time slots** where I can schedule my event.

                    Unavailable times: {json.dumps(user_input, indent=2)}

                    Provide a JSON object structured as:
                    {{
                        "available_times": [
                            {{"date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}
                        ]
                    }}

                    Ensure:
                    - The available slots do **not** overlap with unavailable times.
                    - The slots are at least as long as my requested duration.
                    - The response contains **only** the JSON object, with no additional text or formatting.

                    If no available slots are found, return: {{"available_times": []}}
                    """
                }
            ],
        )

        # Debugging: Print AI response
        print("AI Response for provideDates:", res.message.content)

        response_text = res.message.content[0].text if res.message.content else ""

        # Remove markdown formatting if it exists
        response_text = response_text.strip("```json").strip("```").strip()

        try:
            event_data = json.loads(response_text)  # Convert to dictionary
            return event_data  # Return as Python dict, not JSON string
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail=f"Invalid JSON response: {response_text}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

