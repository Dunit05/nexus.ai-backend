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
    user_id: str
    message: str



@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Store chat messages in Firestore.
    """
    
    bot = chatbot_response(request.message)
    try:
        chat_ref = db.collection("chats").add({
            "user_id": request.user_id,
            "user_message": request.message,
            "bot_response": bot,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return {"message_id": chat_ref[1].id, "bot_response": bot}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/chats/{user_id}")
async def get_chats(user_id: str):
    """
    Fetch all chat messages for a user.
    """
    try:
        chats = db.collection("chats").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
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


# this is an example of how the api routes work
@app.get("/")
async def root():
    return {"message": "Hello World"}


# API endpoint to summarize text and save it to Firestore
@app.post("/summarize")
async def summarize(request: SummarizeRequest):
    """
    Summarize text and save it to Firestore (No authentication required).
    """
    try:
        summary = summarizebot(request.message)

        note_ref = db.collection("summaries").add({
            "user_id": request.user_id,  # ✅ Directly use user_id from request
            "original_text": request.message,
            "summary": summary,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return {"summary": summary, "note_id": note_ref[1].id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# API endpoint to retrieve summaries for a specific user

@app.get("/summaries/{user_id}")
async def get_summaries(user_id: str):
    """
    Fetch all summaries for a specific user (No authentication required).
    """
    try:
        summaries = db.collection("summaries").where("user_id", "==", user_id).order_by(
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
async def checkAvailability(request: AvailabilityRequest):
    """
    Extract event details, find available time slots, and store in Firestore.
    """
    try:
        # Extract event details using AI
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

                    Text: {request.user_input}
                    """
                }
            ],
        )

        response_text = res.message.content[0].text if res.message.content else ""
        response_text = response_text.strip("```json").strip("```").strip()

        # Parse the AI response into event_data
        try:
            event_data = json.loads(response_text)
            if not event_data.get("task_name") or not event_data.get("duration_hours"):
                raise ValueError("Missing required fields in AI response.")
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=500, detail="AI returned invalid JSON.")

        print("✅ Extracted Event Data:", json.dumps(event_data, indent=2))

        # Step 2: Fetch unavailable times
        logic_apps_url = "https://prod-21.northcentralus.logic.azure.com:443/workflows/e1d025b460494c53862f958fe67c0be9/triggers/When_a_HTTP_request_is_received/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=3FElBEyk25j3s6YLw3L2nw45EjCugN7May7ixC6NUWc"
        response = requests.post(logic_apps_url, json=event_data)

        try:
            unavailable_times = response.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Logic Apps returned invalid JSON.")

        print("📅 Unavailable Times:", json.dumps(unavailable_times, indent=2))

        # Step 3: Compute available slots
        available_slots = get_available_slots(unavailable_times, event_data["duration_hours"])
        print("✅ Computed Available Slots:", json.dumps(available_slots, indent=2))

        # Step 4: Select the best time
        selected_time = provideDates(event_data, available_slots)

        # Step 5: Store event details in Firestore
        event_ref = db.collection("events").add({
            "user_id": "test_user",  # Replace with authenticated user ID if using auth
            "task_name": event_data["task_name"],
            "duration_hours": event_data["duration_hours"],
            "week_start": event_data["week_start"],
            "week_end": event_data["week_end"],
            "selected_time": selected_time.get("selected_time", None),
            "available_slots": available_slots["available_times"],
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return {
            "event_id": event_ref[1].id,
            "task_name": event_data["task_name"],
            "available_times": available_slots["available_times"],
            "selected_time": selected_time.get("selected_time", None)
        }

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events/{user_id}")
async def get_events(user_id: str):
    """
    Fetch all events scheduled for a user from Firestore.
    """
    try:
        events_ref = db.collection("events").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()

        return [
            {
                "event_id": event.id,
                "task_name": event.to_dict().get("task_name"),
                "duration_hours": event.to_dict().get("duration_hours"),
                "week_start": event.to_dict().get("week_start"),
                "week_end": event.to_dict().get("week_end"),
                "selected_time": event.to_dict().get("selected_time"),
                "available_slots": event.to_dict().get("available_slots"),
                "timestamp": event.to_dict().get("timestamp")
            }
            for event in events_ref
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



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

@app.get("/test_firestore")
async def test_firestore():
    """
    Test Firestore connection by retrieving all documents from the 'chats' collection.
    """
    try:
        chats_ref = db.collection("chats").limit(1).stream()
        result = [doc.to_dict() for doc in chats_ref]
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))