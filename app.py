import os
import json
import google.auth
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from fastapi import FastAPI, Request, HTTPException
from starlette.responses import RedirectResponse
from features import *


# # Load Google API credentials
# CLIENT_SECRETS_FILE = "credentials.json"
# SCOPES = ["https://www.googleapis.com/auth/calendar"]

# # Store user credentials (in a real app, store this securely)
# USER_CREDENTIALS_FILE = "token.json"

# # OAuth Flow to get the authorization URL
# @app.get("/authorize")
# async def authorize():
#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRETS_FILE,
#         scopes=SCOPES,
#         redirect_uri="http://localhost:8000/oauth2callback"
#     )
#     auth_url, _ = flow.authorization_url(prompt="consent",
#                                          access_type="offline")
#     return RedirectResponse(auth_url)

# # OAuth Callback Route
# @app.get("/oauth2callback")
# async def oauth2callback(request: Request):
#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRETS_FILE,
#         scopes=SCOPES,
#         redirect_uri="http://localhost:8000/oauth2callback"
#     )

#     # Get authorization code from request
#     code = request.query_params.get("code")
#     if not code:
#         raise HTTPException(status_code=400, detail="Authorization code missing")

#     flow.fetch_token(code=code)
#     creds = flow.credentials

#     # Save user credentials
#     with open(USER_CREDENTIALS_FILE, "w") as token:
#         token.write(creds.to_json())

#     return {"message": "Authorization successful! You can now access Google Calendar."}

# # Function to get Google Calendar service
# def get_calendar_service():
#     if not os.path.exists(USER_CREDENTIALS_FILE):
#         raise HTTPException(status_code=401, detail="User not authenticated. Please visit /authorize")

#     creds = Credentials.from_authorized_user_file(USER_CREDENTIALS_FILE, SCOPES)
#     service = build("calendar", "v3", credentials=creds)
#     return service

# # API to Create a New Event
# @app.post("/create_event")
# async def create_event():
#     service = get_calendar_service()

#     event = {
#         "summary": "Meeting with Team",
#         "location": "Online",
#         "description": "Discuss project updates",
#         "start": {
#             "dateTime": "2025-02-05T10:00:00-05:00",
#             "timeZone": "America/Toronto",
#         },
#         "end": {
#             "dateTime": "2025-02-05T11:00:00-05:00",
#             "timeZone": "America/Toronto",
#         },
#         "reminders": {
#             "useDefault": False,
#             "overrides": [{"method": "email", "minutes": 10}],
#         },
#     }

#     event = service.events().insert(calendarId="primary", body=event).execute()
#     return {"event_id": event.get("id"), "event_link": event.get("htmlLink")}

# # API to Get Upcoming Events
# @app.get("/events")
# async def get_events():
#     service = get_calendar_service()
#     events_result = service.events().list(
#         calendarId="primary", maxResults=5, singleEvents=True, orderBy="startTime"
#     ).execute()

#     events = events_result.get("items", [])
#     return events


# Request model / schema for summarization post request
class SummarizeRequest(BaseModel):
    message: str
    user_id: str  # Associate summaries with a user (maybe we can change this to an email later)???

class AvailabilityRequest(BaseModel):
    user_input: str

# API endpoint to summarize text and save it to Firestore
@app.post("/summarize")
async def summarize(request: SummarizeRequest):
    summary = summarizebot(request.message)

    # store in firestore/database the user_id, original_text, summary, timestamp
    note_ref = db.collection("summaries").add({
        "user_id": request.user_id,
        "original_text": request.message,
        "summary": summary,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    # return the summary and note_id from api
    return {"summary": summary, "note_id": note_ref[1].id}

# API endpoint to retrieve summaries for a specific user
@app.get("/summaries/{user_id}")
async def get_summaries(user_id: str):
    # this is basically a query to get all the summaries for a user
    notes = db.collection("summaries").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    
    return [{"note_id": note.id, "original_text": note.to_dict()["original_text"], "summary": note.to_dict()["summary"], "timestamp": note.to_dict()["timestamp"]} for note in notes]

@app.post("/checkAvailability")
def checkAvailability(request: AvailabilityRequest):
    return checkAvailability1(request.user_input)
@app.post("/add_task")
async def add_task(request: SummarizeRequest):
    priority = prioritize_task(request.message)

    task_ref = db.collection("tasks").add({
        "user_id": request.user_id,
        "task": request.message,
        "priority": priority,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    return {"task": request.message, "priority": priority, "task_id": task_ref[1].id}

@app.get("/tasks/{user_id}")
async def get_tasks(user_id: str):
    try:
        tasks = db.collection("tasks").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()

        return [
            {
                "task_id": task.id,
                "task": task.to_dict().get("task"),
                "priority": task.to_dict().get("priority"),
                "timestamp": task.to_dict().get("timestamp")
            }
            for task in tasks
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/add_reminder")
async def add_reminder(request: SummarizeRequest):
    note_ref = db.collection("reminders").add({
        "user_id": request.user_id,
        "reminder_text": request.message,
        "repeat": "weekly",  # Options: daily, weekly, monthly
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    return {"reminder_text": request.message, "repeat": "weekly", "reminder_id": note_ref[1].id}

@app.get("/reminders/{user_id}")
async def get_reminders(user_id: str):
    try:
        reminders = db.collection("reminders").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()

        return [
            {
                "reminder_id": reminder.id,
                "reminder_text": reminder.to_dict().get("reminder_text"),
                "repeat": reminder.to_dict().get("repeat"),
                "timestamp": reminder.to_dict().get("timestamp")
            }
            for reminder in reminders
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# this is an example of how the api routes work
@app.get("/")
async def root():
    return {"message": "Hello World"}