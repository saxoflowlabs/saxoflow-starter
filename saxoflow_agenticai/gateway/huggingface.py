import os
import requests
from dotenv import load_dotenv
from saxoflow_agenticai.gateway.base import ModelGateway

load_dotenv()

class HuggingFaceGateway(ModelGateway):
    def __init__(self, model_name):
        self.api_key = os.getenv("HUGGINGFACE_API_KEY")
        self.model = model_name
        self.url = f"https://api-inference.huggingface.co/models/{self.model}"
        if not self.api_key:
            raise ValueError("HUGGINGFACE_API_KEY not set in environment.")

    def query(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # Some chat models accept {"inputs": [{"role": "user", "content": ...}]}
        # For generic text models, use: {"inputs": prompt}
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": 0.2,
                "max_new_tokens": 8192
            }
        }
        response = requests.post(self.url, headers=headers, json=payload)
        if response.status_code != 200:
            print("❌ HuggingFace API call failed:", response.status_code)
            print("📨", response.text)
            response.raise_for_status()
        # The response can be: [{"generated_text": "..."}] for plain text, or check docs for chat structure
        data = response.json()
        if isinstance(data, list) and "generated_text" in data[0]:
            return data[0]["generated_text"].strip()
        elif "error" in data:
            return f"[HuggingFace Error] {data['error']}"
        else:
            return str(data)
