import os
import json
import google.auth
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from fastapi import FastAPI, Request, HTTPException
from starlette.responses import RedirectResponse
from features import *

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