import cohere
import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends, Request, File, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import json
import requests
from vector_rag import *

# Load environment variables
load_dotenv()
coherekey = os.getenv("COHERE_API_KEY")
if not coherekey:
    raise ValueError("COHERE_API_KEY not found in environment variables")

# Initialize Cohere client
co = cohere.ClientV2(api_key=coherekey)

# Initialize Firestore
cred = credentials.Certificate("firebase_credentials.json")
# Initialize Firebase Admin SDK (Only run once)
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    print("Firebase already initialized.")

# Firestore client
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
    
from datetime import datetime, timedelta

def get_available_slots(unavailable_times, duration_hours):
    """
    Given a list of unavailable times, compute the available slots for scheduling.
    """

    if not unavailable_times.get("events"):  # If no events exist, return the full day as available
        return {
            "available_times": [
                {"date": "2025-02-05", "start_time": "00:00", "end_time": "23:59"}
            ]
        }

    from datetime import datetime, timedelta

    # Convert unavailable times into sorted (start, end) tuples
    busy_times = sorted(
        [
            (
                datetime.fromisoformat(event["Start"].split("+")[0]),
                datetime.fromisoformat(event["End"].split("+")[0]),
            )
            for event in unavailable_times.get("events", [])
        ],
        key=lambda x: x[0],
    )

    # Define full day range
    start_of_day = busy_times[0][0].replace(hour=0, minute=0, second=0)
    end_of_day = busy_times[0][0].replace(hour=23, minute=59, second=59)

    available_slots = []
    prev_end = start_of_day

    # Compute free slots
    for start, end in busy_times:
        if prev_end + timedelta(hours=duration_hours) <= start:
            available_slots.append(
                {
                    "date": prev_end.date().isoformat(),
                    "start_time": prev_end.strftime("%H:%M"),
                    "end_time": (prev_end + timedelta(hours=duration_hours)).strftime("%H:%M"),
                }
            )
        prev_end = max(prev_end, end)

    # Check after the last event
    if prev_end + timedelta(hours=duration_hours) <= end_of_day:
        available_slots.append(
            {
                "date": prev_end.date().isoformat(),
                "start_time": prev_end.strftime("%H:%M"),
                "end_time": (prev_end + timedelta(hours=duration_hours)).strftime("%H:%M"),
            }
        )

    return {"available_times": available_slots}

def chatbot_response(user_input: str) -> str:
    try:
        res = co.chat(
            model="command-r7b-12-2024",
            messages=[
                {
                    "role": "user",
                    "content": user_input,
                }
            ],
        )
        return res.message.content[0].text
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def checkAvailability1(user_input: str):
    try:
        # Step 1: Extract Task Information
        res = co.chat(
            model="command-r-plus",
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    Extract scheduling details and return a JSON object:
                    {{
                        "task_name": "<Task Name>",
                        "duration_hours": <Duration in hours (positive number)>,
                        "week_start": "<YYYY-MM-DD>",
                        "week_end": "<YYYY-MM-DD>"
                    }}

                    Respond with ONLY the JSON object. No explanations, formatting, or extra text.
                    If extraction fails, return: {{}}.

                    Text: {user_input}
                    """
                }
            ],
        )

        response_text = res.message.content[0].text if res.message.content else ""
        response_text = response_text.strip("```json").strip("```").strip()

        # Step 2: Parse AI Response
        try:
            event_data = json.loads(response_text)
            if not event_data.get("task_name") or not event_data.get("duration_hours"):
                raise ValueError("Missing required fields in AI response.")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=500, detail="AI returned invalid JSON.")

        print("✅ Extracted Event Data:", json.dumps(event_data, indent=2))

        # Step 3: Fetch Unavailable Times from Logic Apps
        logic_apps_url = "https://prod-21.northcentralus.logic.azure.com:443/workflows/e1d025b460494c53862f958fe67c0be9/triggers/When_a_HTTP_request_is_received/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=3FElBEyk25j3s6YLw3L2nw45EjCugN7May7ixC6NUWc"
        response = requests.post(logic_apps_url, json=event_data)

        try:
            unavailable_times = response.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Logic Apps returned invalid JSON.")

        print("📅 Unavailable Times:", json.dumps(unavailable_times, indent=2))

        # Step 4: Compute Available Slots
        available_slots = get_available_slots(unavailable_times, event_data["duration_hours"])
        print("✅ Computed Available Slots:", json.dumps(available_slots, indent=2))

        # Step 5: Find the Best Time
        selected_time = provideDates(event_data, available_slots)

        # Step 6: Return response in the correct format
        return {
            "available_times": available_slots["available_times"],  # Send all available slots
            "selected_time": selected_time.get("selected_time", None),  # Best slot selected
        }

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



def provideDates(event_data, available_slots):
    try:
        res = co.chat(
            model="command-r-plus",
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    Based on the available time slots, select the best time for scheduling the event: "{event_data['task_name']}".

                    **Event Duration:** {event_data['duration_hours']} hours  
                    **Available Slots:** {json.dumps(available_slots, indent=2)}

                    Respond with only the JSON:
                    {{
                        "selected_time": {{"date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}
                    }}

                    If no suitable time is found, return:
                    {{"selected_time": null}}
                    """
                }
            ],
        )

        # Debugging: Print AI response
        response_text = res.message.content[0].text if res.message.content else ""
        response_text = response_text.strip("```json").strip("```").strip()

        try:
            selected_slot = json.loads(response_text)
            return selected_slot  # Return as Python dict, not JSON string
        except json.JSONDecodeError:
            print(f"❌ ERROR: AI returned invalid JSON → {response_text}")
            raise HTTPException(status_code=500, detail="AI returned invalid JSON.")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def verify_firebase_token(authorization: str = Header(None)):
    """
    Verifies the Firebase Authentication Token and extracts user info.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    token = authorization.split("Bearer ")[-1]  # Extract token
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token  # Contains user details (uid, email)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    
@app.post("/add_pdf/{user_id}")
async def add_pdf(user_id: str, file: UploadFile = File(...)):
    """
    Upload a PDF, extract text, and store embeddings in Pinecone under user-specific index.
    """
    try:
        # Save uploaded file temporarily
        file_path = f"temp_{file.filename}"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # Store in Pinecone under user_id
        add_new_pdf(file_path, user_id)
        os.remove(file_path)  # Delete temp file
        
        return {"message": f"PDF added to Pinecone under index {user_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete_index/{user_id}")
async def delete_index(user_id: str):
    """
    Delete all vectors in the user's Pinecone index.
    """
    try:
        delete_pinecone_index(user_id)
        return {"message": f"All vectors in {user_id} index deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query_rag/{user_id}")
async def query_rag(user_id: str, query: str):
    """
    Retrieve AI-generated answers from the user's Pinecone index.
    """
    try:
        answer = generate_rag_answer(query, user_id)
        return {"query": query, "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))