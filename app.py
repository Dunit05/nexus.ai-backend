import os
import json
import google.auth
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from starlette.responses import RedirectResponse
from features import *

# Request model / schema for summarization post request
class SummarizeRequest(BaseModel):
    message: str
    user_id: str  # Associate summaries with a user (maybe we can change this to an email later)???

class AvailabilityRequest(BaseModel):
    user_input: str
    
class ChatRequest(BaseModel):
    user_id: str  # Store conversations per user
    message: str  # User's message



@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(verify_firebase_token)):
    """
    Chat API that requires Firebase Authentication.
    """
    try:
        res = co.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": request.message}],
        )

        bot_response = res.message.content[0].text if res.message.content else "I'm not sure how to respond."

        # ✅ Use Firebase UID instead of user_id from request
        chat_ref = db.collection("chats").add({
            "user_id": user["uid"],  # Store Firebase UID
            "user_message": request.message,
            "bot_response": bot_response,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return {"message_id": chat_ref[1].id, "bot_response": bot_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    
@app.get("/chats/{user_id}")
async def get_chat_history(user: dict = Depends(verify_firebase_token)):
    """
    Fetch chat history for the authenticated user.
    """
    try:
        chats = db.collection("chats").where("user_id", "==", user["uid"]).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()

        return [
            {
                "message_id": chat.id,
                "user_message": chat.to_dict().get("user_message"),
                "bot_response": chat.to_dict().get("bot_response"),
                "timestamp": chat.to_dict().get("timestamp")
            }
            for chat in chats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_current_user(authorization: str = Header(None)):
    """
    FastAPI dependency to extract and verify Firebase Authentication token.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    token = authorization.split("Bearer ")[-1]  # Extract token from "Bearer <token>"
    user_data = verify_firebase_token(token)  # Validate token
    return user_data  # Returns user details

# ✅ Protect /chat with Firebase authentication
@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Chat API that requires Firebase Authentication.
    """
    try:
        # Send user input to Cohere AI
        res = co.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": request.message}],
        )

        bot_response = res.message.content[0].text if res.message.content else "I'm not sure how to respond."

        # Store chat history in Firestore
        chat_ref = db.collection("chats").add({
            "user_id": user["uid"],  # Use Firebase UID instead of user_id from request
            "user_message": request.message,
            "bot_response": bot_response,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return {"message_id": chat_ref[1].id, "bot_response": bot_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# this is an example of how the api routes work
@app.get("/")
async def root():
    return {"message": "Hello World"}


# API endpoint to summarize text and save it to Firestore
@app.post("/summarize")
async def summarize(request: SummarizeRequest, user: dict = Depends(get_current_user)):
    """
    Summarize text and associate it with the authenticated Firebase user.
    """
    summary = summarizebot(request.message)

    note_ref = db.collection("summaries").add({
        "user_id": user["uid"],  # Use Firebase UID
        "original_text": request.message,
        "summary": summary,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    return {"summary": summary, "note_id": note_ref[1].id}

# API endpoint to retrieve summaries for a specific user

@app.get("/summaries")
async def get_summaries(user: dict = Depends(verify_firebase_token)):
    """
    Fetch all summaries for the authenticated user using email instead of UID.
    """
    try:
        user_email = user.get("email")  # ✅ Extract email from Firebase token
        if not user_email:
            raise HTTPException(status_code=400, detail="User email not found")

        summaries = db.collection("summaries").where("user_id", "==", user_email).order_by(
            "timestamp", direction=firestore.Query.DESCENDING
        ).stream()

        return [
            {
                "note_id": summary.id,
                "original_text": summary.to_dict().get("original_text"),
                "summary": summary.to_dict().get("summary"),
                "timestamp": summary.to_dict().get("timestamp"),
            }
            for summary in summaries
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug_user")
async def debug_user(user: dict = Depends(verify_firebase_token)):
    return user  # ✅ Check what Firebase is returning


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
