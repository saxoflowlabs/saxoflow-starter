import os
import requests
from dotenv import load_dotenv
from saxoflow_agenticai.gateway.base import ModelGateway

load_dotenv()

class GoogleAIStudioGateway(ModelGateway):
    def __init__(self, model_name):
        self.api_key = os.getenv("GOOGLEAISTUDIO_API_KEY")
        self.model = model_name  # e.g., "gemini-2.0-flash"
        if not self.api_key:
            raise ValueError("GOOGLEAISTUDIO_API_KEY not set in environment.")
        # Always use /models/{model}:generateContent
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def query(self, prompt: str) -> str:
        headers = {
            "Content-Type": "application/json"
        }
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192
            }
        }
        response = requests.post(self.url, headers=headers, json=body)
        if response.status_code != 200:
            print("❌ GoogleAIStudio API call failed:", response.status_code)
            print("📨", response.text)
            response.raise_for_status()
        data = response.json()
        return (
            data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if data.get("candidates")
            else "[No response from Gemini]"
        )
