#!/usr/bin/env python3
import os
import sys
sys.stdout.flush()

print("加载环境变量...", flush=True)
from dotenv import load_dotenv
load_dotenv()

print("导入库...", flush=True)
from notion_client import Client
from openai import OpenAI

print("初始化客户端...", flush=True)
# 初始化客户端
notion = Client(auth=os.getenv("NOTION_API_TOKEN"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

print("查询未分析视频...", flush=True)
# 获取第一个未分析的视频
response = notion.databases.query(
    database_id=os.getenv("NOTION_DATABASE_ID"),
    page_size=1,
    filter={
        "property": "技术分类",
        "multi_select": {
            "is_empty": True
        }
    }
)

print(f"找到 {len(response['results'])} 个视频", flush=True)

if not response["results"]:
    print("没有未分析的视频", flush=True)
    exit()

page = response["results"][0]
bvid = page["properties"]["BV号"]["rich_text"][0]["plain_text"].strip()
title = page["properties"]["Title"]["title"][0]["plain_text"]
page_id = page["id"]

print(f"第一个视频: {title} [{bvid}]", flush=True)

# 测试AI分析
print("测试AI分析...", flush=True)
prompt = f"""
请分析以下巴西柔术相关的视频内容，提取以下信息：
1. 技术分类：视频中主要演示的巴西柔术技术类别，比如：guard, side control, mount, back take, 降服, 扫倒, 逃脱, 过腿等，最多2个标签
2. 核心动作要点：列出3个最关键的动作要点，每个要点不超过20字

内容：标题: {title}
简介: 这是一个巴西柔术教学视频

请严格按照JSON格式返回，不要有其他内容：
{{
    "技术分类": ["标签1", "标签2"],
    "核心动作要点": [
        "动作要点1",
        "动作要点2", 
        "动作要点3"
    ]
}}
"""

response = openai_client.chat.completions.create(
    model=os.getenv("OPENAI_MODEL"),
    messages=[
        {"role": "system", "content": "你是一个专业的巴西柔术黑带教练，擅长分析技术动作，提取关键信息。"},
        {"role": "user", "content": prompt}
    ],
    temperature=0.3
)

print("AI返回结果:", response.choices[0].message.content, flush=True)
print("✅ 所有步骤正常！", flush=True)
