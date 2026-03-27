import requests
import json
from src.config import settings

def test_zai_raw():
    url = f"{settings.ZAI_API_BASE}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.ZAI_API_KEY}"
    }
    data = {
        "model": "glm-5",
        "messages": [
            {"role": "user", "content": "Hello, are you there?"}
        ]
    }
    
    print(f"Testing URL: {url}")
    print(f"Headers: {json.dumps({k: (v[:5] + '...' if k == 'Authorization' else v) for k, v in headers.items()})}")
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_zai_raw()
