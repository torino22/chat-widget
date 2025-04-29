from fastapi import FastAPI, HTTPException, File, UploadFile
import requests
from transformers import pipeline
import torch 
import time
from fastapi.middleware.cors import CORSMiddleware
from requests.auth import HTTPBasicAuth
from typing import List
from pydantic import BaseModel
from openai import OpenAI
from database import get_connection
import re
import json
import os
from dotenv import load_dotenv

load_dotenv()
# Initialize API with your key
API_KEY = os.getenv("API_KEY")
client = OpenAI(api_key=API_KEY)

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define request model
class PromptRequest(BaseModel):
    prompt: str
    conversationHistory: List[dict] = []
    
    
def validate_email(email: str):
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return {"is_valid": False, "reason": "invalid email format"}
    return {"is_valid": True, "reason": ""}

def validate_phone(phone: str):
    if not re.match(r'^\+?\d{7,15}$', phone):
        return {"is_valid": False, "reason": "invalid phone number format"}
    return {"is_valid": True, "reason": ""}


functions = [
    {
        "name": "validate_email",
        "description": "Validates if a given input is a proper email address",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "The email to validate"}
            },
            "required": ["email"]
        }
    },
    {
        "name": "validate_phone",
        "description": "Validates if a given input is a proper phone number",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "The phone number to validate"}
            },
            "required": ["phone"]
        }
    }
]


@app.post("/api/message")
async def query_openai(data: PromptRequest):
    messages = data.conversationHistory or [
        {
            "role": "system",
            "content": '''
You're the Soft Suave onboarding companion! Congrats on your new role 🎉 As you settle in, I'll guide you step-by-step to gather everything we need:

1. Full legal name (so we get your paperwork right 😉)
2. Preferred name (if you go by something else)
3. Employee ID (you'll find this in your offer letter)
4. Start date (YYYY-MM-DD)
5. Personal email address
6. Mobile phone number
7. Mailing address (Street, City, State, ZIP)
8. Bank details for payroll (account & routing numbers)
9. Tax ID (e.g., SSN)
10. Emergency contact (Name, Relationship, Phone)
11. Equipment requests (e.g., laptop, monitors, software access)

How this works:
- I'll ask one detail at a time, and wait until it's formatted correctly.
- If something doesn't look right, I'll say, “Hmm, that doesn't seem valid for [Detail]. Could you try again?”
- Once each item is confirmed, we'll move on.
- After we have everything, I'll send you a neat summary to double-check:
```
Onboarding details confirmation
Full Name: {Full legal name}
Preferred Name: {Preferred name}
Employee ID: {Employee ID}
Start Date: {Start date}
Email: {Personal email}
Phone: {Phone number}
Address: {Mailing address}
Bank Account: {Bank details}
Tax ID: {Tax ID}
Emergency Contact: {Emergency contact}
Equipment Needs: {Equipment requests}
```
That's it—just let me know the first thing: your full legal name!
'''
        }
    ]
    
    prompt = data.prompt
    
    try:
        # Add user message to conversation
        messages.append({"role": "user", "content": prompt})
        
        # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            functions=functions,
            function_call="auto"
        )
        
        # Get the response
        response_message = response.choices[0].message
        
        if response_message.function_call:
            func_name = response_message.function_call.name
            arguments = json.loads(response_message.function_call.arguments)


            if func_name == "validate_email":
                result = validate_email(arguments["email"])
            elif func_name == "validate_phone":
                result = validate_phone(arguments["phone"])
            else:
                result = {"is_valid": False, "reason": "Unknown function"}

            # Send function response back to GPT
            func_response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages + [
                    {
                        "role": "function",
                        "name": func_name,
                        "content": json.dumps(result)
                    }
                ]
            )
            final_response = func_response.choices[0].message.content

            messages.append({"role": "assistant", "content": final_response})

            return {"conversationHistory": messages}

        else:
            final_response = response_message.content
            messages.append({"role": "assistant", "content": final_response})

            return {"conversationHistory": messages}
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            "error": str(e), 
            "conversationHistory": messages,
            "response": {
                "id": 0,
                "text": f"Error: {str(e)}",
                "isAI": True
            }
        }


class Lead(BaseModel):
    name: str
    email: str
    requirement: str
    company: str
    phone: str
    meetingslot: str

@app.post("/api/leads")
def create_lead(lead: Lead):
  try:
    conn = get_connection()
    cursor = conn.cursor()

    sql = "INSERT INTO leads (name, email, requirement, company, phone, meetingslot) VALUES (%s, %s, %s, %s, %s, %s)"
    values = (lead.name, lead.email, lead.requirement, lead.company, lead.phone, lead.meetingslot)

    cursor.execute(sql, values)
    conn.commit()

    return {"message": "Lead saved successfully!"}

  except Exception as e:
    print(f"Database Error: {e}")
    return {"error": str(e)}

  finally:
    cursor.close()
    conn.close()



class MeetingInvitee(BaseModel):
    email: str

class Settings(BaseModel):
    meeting_invitees: List[MeetingInvitee]
    email_notification: bool
    contact_email: str
    contact_name: str

class CreateMeetingRequest(BaseModel):
    start_time: str          # ISO8601 datetime
    timezone: str            # e.g. "America/Los_Angeles"
    topic: str               # Meeting topic
    type: int                # Meeting type (e.g. 2 = scheduled)
    agenda: str              # Meeting agenda
    duration: int            # Duration in minutes
    settings: Settings       # Nested settings block


token_data = {
    "access_token": None,
    "expires_at": 0,  # Unix timestamp
}

ZOOM_CLIENT_ID     = 'CAi9VUMuSBaQWVflliHUQw'
ZOOM_CLIENT_SECRET = 'cfU2p2KUeHfF71UyBerbfsbHK81e0423'
ZOOM_ACCOUNT_ID = 'DyB116CjTfWXUNkSAmf-2w'

def get_valid_access_token():
    now = time.time()
    # Return existing token if still valid
    if token_data["access_token"] and now < token_data["expires_at"]:
        return token_data["access_token"]

    # Fetch a fresh token via client_credentials grant
    resp = requests.post(
        "https://zoom.us/oauth/token",
        params={
            "grant_type": "account_credentials",
            "account_id": ZOOM_ACCOUNT_ID
        },
        auth=HTTPBasicAuth(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET),
    )
    try:
        resp.raise_for_status()
    except Exception:
        raise HTTPException(401, f"Failed to fetch Zoom token: {resp.text}")

    body = resp.json()
    token_data["access_token"] = body["access_token"]
    token_data["expires_at"]   = now + body["expires_in"]
    return token_data["access_token"]


@app.post("/zoom/create_meeting")
def create_zoom_meeting(req: CreateMeetingRequest):
    """
    Create a Zoom meeting using server-to-server OAuth (client_credentials).
    """
    access_token = get_valid_access_token()

    # Build payload directly from the validated request
    payload = req.model_dump()

    response = requests.post(
        "https://api.zoom.us/v2/users/me/meetings",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if response.status_code != 201:
        raise HTTPException(400, f"Zoom meeting creation failed: {response.text}")

    return response.json()

asr = pipeline(
  "automatic-speech-recognition",
  model="openai/whisper-large-v3-turbo",
  chunk_length_s=30,       # optional: chunk long audios
  device="cuda" if torch.cuda.is_available() else "cpu"
)

@app.post("/transcribe/")
async def transcribe(file: UploadFile = File(...)):
    """Accepts audio upload and returns transcription"""
    audio_bytes = await file.read()
    try:
        # Directly pass raw bytes to pipeline (avoids file I/O)
        result = asr(audio_bytes)
        return {"text": result.get("text", "")}  
    except Exception as e:
        # Log full traceback to server console
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")
