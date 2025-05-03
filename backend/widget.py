from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
from openai import OpenAI
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

