from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
import ffmpeg, io, soundfile as sf, traceback
from typing import List
from pydantic import BaseModel
from openai import OpenAI
import re
import json
from fastapi.responses import FileResponse
import asyncio
import edge_tts
import uuid
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

model = WhisperModel("large-v3", device="cpu", compute_type="int8")

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
4. Start date (either YYYY-MM-DD or how someone would say it with month name and date and year )
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

def decode_webm_to_pcm(audio_bytes: bytes):
    """
    In-memory decode from WebM/Opus → WAV/PCM (16kHz, mono).
    Returns: (numpy.ndarray, sample_rate)
    """
    try:
        # Run ffmpeg to convert input bytes (pipe:0) to wav bytes (pipe:1)
        wav_bytes, _ = (
            ffmpeg
            .input("pipe:0")
            .output("pipe:1",
                    format="wav",
                    acodec="pcm_s16le",
                    ac=1,
                    ar="16000")
            .run(input=audio_bytes, capture_stdout=True, capture_stderr=True)
        )
        # Now read those wav bytes into numpy
        audio_arr, sr = sf.read(io.BytesIO(wav_bytes))
        return audio_arr, sr

    except ffmpeg.Error as e:
        # ffmpeg stderr is in e.stderr
        raise RuntimeError(f"FFmpeg decoding error: {e.stderr.decode()}")

@app.post("/transcribe/")
async def transcribe(file: UploadFile = File(...)):
    """Accepts WebM/Opus upload and returns transcription"""
    audio_bytes = await file.read()

    try:
        # 1️⃣ Decode WebM → PCM
        audio_data, sample_rate = decode_webm_to_pcm(audio_bytes)

        # 2️⃣ Transcribe with chunking + VAD
        segments, info = model.transcribe(
            audio_data
        )

        # 3️⃣ Concatenate segment texts
        text = " ".join(seg.text for seg in segments).strip()
        return {"text": text}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")
    
class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-JennyNeural"  # Default voice

@app.post("/tts/")
async def generate_tts(request: TTSRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    filename = f"tts_{uuid.uuid4().hex}.mp3"
    filepath = f"./{filename}"

    try:
        communicate = edge_tts.Communicate(text, voice=request.voice)
        await communicate.save(filepath)
        return FileResponse(filepath, media_type="audio/mpeg", filename="output.mp3")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")
