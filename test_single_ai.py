from dotenv import load_dotenv
load_dotenv()
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

print("测试AI相关性判断...")
prompt = """
请判断这个视频是不是真正的巴西柔术(BJJ)技术相关视频：
视频标题：巴西柔术基础入门教学
视频简介：本视频详细讲解巴西柔术的基础姿势、guard防守技巧和基本降服动作，适合新手学习。

判断规则：
✅ 是巴西柔术相关：包含巴西柔术技术教学、实战演示、技巧讲解、训练方法、比赛技术分析等内容
❌ 不是相关：普通柔韧性训练、压胯、摔跤、柔道、普通搏击比赛、搞笑视频、 unrelated内容

只返回JSON，不要其他内容：
{"is_related": true/false}
"""

try:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL"),
        messages=[
            {"role": "system", "content": "你是一个专业的巴西柔术内容审核员，只判断内容是否相关。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )
    print("✅ AI调用成功")
    print("返回结果:", response.choices[0].message.content)
except Exception as e:
    print("❌ AI调用失败")
    print("错误:", str(e))
