import os
from litellm import completion

os.environ["ZHIPUAI_API_KEY"] = "10961f6dcd11491596cb665061971d99.VGiyR7D0E9Oo83hz"

try:
    response = completion(
        model="glm-4-flash",
        api_base="https://open.bigmodel.cn/api/paas/v4/",
        custom_llm_provider="openai",
        messages=[{"role": "user", "content": "hello"}],
    )
    print("SUCCESS: ", response.choices[0].message.content)
except Exception as e:
    print("ERROR: ", str(e))
