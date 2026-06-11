from dotenv import load_dotenv
load_dotenv()
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

try:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL"),
        messages=[
            {"role": "user", "content": "你好，测试一下"}
        ]
    )
    print("✅ API调用成功！")
    print("返回结果:", response.choices[0].message.content)
except Exception as e:
    print("❌ API调用失败")
    print("错误信息:", str(e))
    
    # 尝试换个模型名
    print("\n尝试使用qwen-plus模型...")
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "user", "content": "你好，测试一下"}
            ]
        )
        print("✅ qwen-plus调用成功！")
    except Exception as e2:
        print("❌ qwen-plus也失败:", str(e2))
