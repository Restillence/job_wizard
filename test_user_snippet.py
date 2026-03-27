import litellm
import os
from src.config import settings

# Set your Z AI API Key
os.environ['ZAI_API_KEY'] = settings.ZAI_API_KEY

print(f"Using Key: {settings.ZAI_API_KEY[:5]}...")

try:
    # Call GLM-5
    response = litellm.completion(
        model="zai/glm-5",
        messages=[
            {"role": "user", "content": "Hello, how does GLM-5 compare to other open models?"}
        ]
    )
    print("Success!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
