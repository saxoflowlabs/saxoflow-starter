import os
import requests
from dotenv import load_dotenv
from saxoflow_agenticai.gateway.base import ModelGateway

load_dotenv()

class MistralGateway(ModelGateway):
    def __init__(self, model_name: str):
        self.api_key = os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY not found in environment variables.")
        self.model = model_name
        self.url = "https://api.mistral.ai/v1/chat/completions"

    def query(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 8192
        }
        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            print(f"❌ Mistral API request failed: {e}")
            if response is not None:
                print("📨 Response:", response.text)
            raise
