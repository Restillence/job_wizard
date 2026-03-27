from src.config import settings
import os

print(f"Current Working Directory: {os.getcwd()}")
print(f".env exists: {os.path.exists('.env')}")
print(f"ZAI_API_KEY loaded: {bool(settings.ZAI_API_KEY)}")
print(f"ZAI_API_BASE: {settings.ZAI_API_BASE}")
