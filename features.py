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
                    "content": f"Convert this text into a JSON-like object with the fields 'task_name', 'duration_hours', 'week_start', and 'week_end'."
                               f" Ensure the output is a plain text string, without markdown formatting, code blocks, or explanations."
                               f" If you don't know how to respond, return: {{}}.\n"
                               f"Text: {user_input}"
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
            print(event_data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail=f"Invalid JSON response: {response_text}")

        logic_apps_url = "https://prod-21.northcentralus.logic.azure.com:443/workflows/e1d025b460494c53862f958fe67c0be9/triggers/When_a_HTTP_request_is_received/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=3FElBEyk25j3s6YLw3L2nw45EjCugN7May7ixC6NUWc"
        response = requests.post(logic_apps_url, json=event_data)
        available_dates = response.json()
        # show events
        # print(available_dates)
        # with open("file.json", "w") as f:
        #     json.dump(available_dates, f, indent=2)

        request = f"""
        I want to schedule the following event:
        {event_data}

        Please note that I am **unavailable** during the following times:

        {json.dumps(available_dates, indent=2)}

        Kindly suggest a suitable time outside of these unavailable slots.
        """

        # Call provideDates and return JSON instead of string
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
                    "content": f"Return a JSON object with exactly five available time slots for the event. The object should have the structure:\n"
                               f'{{"available_times": [{{"date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}]}}.\n'
                               f"Do not include any explanations, formatting, or text outside this structure. If you can't provide the response, return: {{}}.\n"
                               f"Input: {user_input}"
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
