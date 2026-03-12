import os
from litellm import completion

os.environ["ZAI_API_KEY"] = "10961f6dcd11491596cb665061971d99.VGiyR7D0E9Oo83hz"

try:
    response = completion(
        model="zai/glm-4", messages=[{"role": "user", "content": "hello"}]
    )
    print("SUCCESS: ", response.choices[0].message.content)
except Exception as e:
    print("ERROR: ", str(e))
