#!/usr/bin/env python3
import os
import re
import json
import requests
from dotenv import load_dotenv
from notion_client import Client
from openai import OpenAI
from datetime import datetime
from typing import List, Dict, Optional

# 加载环境变量
load_dotenv()

# 配置常量
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# 初始化客户端
notion = Client(auth=NOTION_API_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


def get_unanalyzed_videos() -> List[Dict]:
    """获取还没有AI分析的视频（技术分类为空）"""
    videos = []
    has_more = True
    next_cursor = None
    
    while has_more:
        response = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            cursor=next_cursor,
            filter={
                "property": "技术分类",
                "multi_select": {
                    "is_empty": True
                }
            }
        )
        
        for page in response["results"]:
            # 获取BV号
            bvid_property = page["properties"].get("BV号", {})
            if bvid_property.get("rich_text"):
                bvid = bvid_property["rich_text"][0]["plain_text"].strip()
                if bvid and bvid.startswith("BV"):
                    videos.append({
                        "page_id": page["id"],
                        "bvid": bvid,
                        "title": page["properties"]["Title"]["title"][0]["plain_text"]
                    })
        
        has_more = response["has_more"]
        next_cursor = response["next_cursor"]
    
    return videos


def get_video_info(bvid: str) -> Optional[Dict]:
    """获取视频详细信息"""
    url = "https://api.bilibili.com/x/web-interface/view"
    params = {"bvid": bvid}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}/"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data["code"] != 0:
            print(f"获取视频信息失败: {data['message']}")
            return None
        
        return data["data"]
    except Exception as e:
        print(f"获取视频信息出错: {e}")
        return None


def get_video_cc_subtitle(bvid: str, cid: int) -> Optional[str]:
    """获取视频CC字幕"""
    url = "https://api.bilibili.com/x/player/v2"
    params = {
        "bvid": bvid,
        "cid": cid
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}/"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data["code"] != 0:
            print(f"获取字幕信息失败: {data['message']}")
            return None
        
        # 查找字幕列表
        subtitle_info = data["data"].get("subtitle", {})
        subtitles = subtitle_info.get("subtitles", [])
        
        if not subtitles:
            return None
        
        # 优先选择中文字幕
        zh_subtitle = None
        for sub in subtitles:
            if sub["lan"] in ["zh", "zh-CN", "cn"]:
                zh_subtitle = sub
                break
        
        if not zh_subtitle:
            zh_subtitle = subtitles[0]  # 没有中文就选第一个
        
        # 下载字幕内容
        subtitle_url = f"https:{zh_subtitle['subtitle_url']}"
        subtitle_response = requests.get(subtitle_url, headers=headers)
        subtitle_response.raise_for_status()
        subtitle_data = subtitle_response.json()
        
        # 拼接字幕文本
        full_text = ""
        for item in subtitle_data["body"]:
            full_text += item["content"] + " "
        
        return full_text.strip()
    except Exception as e:
        print(f"获取CC字幕出错: {e}")
        return None


def is_bjj_related(video_info: Dict) -> bool:
    """AI判断视频是否是真正的巴西柔术技术相关视频"""
    title = video_info["title"]
    desc = video_info["desc"][:500]  # 只取前500字简介
    
    prompt = f"""
请判断这个视频是不是真正的巴西柔术(BJJ)技术相关视频：
视频标题：{title}
视频简介：{desc}

判断规则：
✅ 是巴西柔术相关：包含巴西柔术技术教学、实战演示、技巧讲解、训练方法、比赛技术分析等内容
❌ 不是相关：普通柔韧性训练、压胯、摔跤、柔道、普通搏击比赛、搞笑视频、 unrelated内容

只返回JSON，不要其他内容：
{{"is_related": true/false}}
"""
    
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "你是一个专业的巴西柔术内容审核员，只判断内容是否相关。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip()
        # 解析JSON
        try:
            data = json.loads(result)
            return data.get("is_related", False)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("is_related", False)
            # 如果解析失败，保守判断为不相关
            return False
    except Exception as e:
        print(f"相关性判断出错: {e}")
        return False


def analyze_content_with_ai(content: str) -> Optional[Dict]:
    """使用大模型分析内容，提取技术分类、核心动作要点"""
    prompt = f"""
请分析以下巴西柔术相关的视频内容，提取以下信息：
1. 技术分类：视频中主要演示的巴西柔术技术类别，比如：guard, side control, mount, back take, 降服, 扫倒, 逃脱, 过腿, 摔法, 防守等，最多2个标签
2. 核心动作要点：列出3个最关键的动作要点，每个要点不超过20字

内容：{content}

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
    
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "你是一个专业的巴西柔术黑带教练，擅长分析技术动作，提取关键信息。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        result = response.choices[0].message.content.strip()
        # 解析JSON
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            print(f"AI返回结果解析失败: {result}")
            return None
    except Exception as e:
        print(f"调用AI分析出错: {e}")
        return None


def update_notion_page(page_id: str, ai_analysis: Dict, content_text: str, video_info: Dict, is_related: bool) -> bool:
    """更新已存在的Notion页面，添加AI分析结果"""
    try:
        # 转换时长格式
        duration_seconds = int(video_info["duration"])
        duration_str = f"{duration_seconds//60}:{duration_seconds%60:02d}"
        
        # 构造更新的属性
        properties = {
            "状态": {
                "select": {
                    "name": "已处理" if is_related else "无关视频"
                }
            }
        }
        
        if is_related and ai_analysis:
            properties.update({
                "技术分类": {
                    "multi_select": [{"name": tag} for tag in ai_analysis["技术分类"]]
                }
            })
            
            # 添加技术要点
            tech_points = "\n".join(ai_analysis["核心动作要点"])
            properties["技术要点"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": tech_points
                        }
                    }
                ]
            }
        
        # 先更新属性
        notion.pages.update(
            page_id=page_id,
            properties=properties
        )
        
        # 如果是相关视频且有分析结果，添加内容
        if is_related and ai_analysis:
            # 构造页面内容
            children = [
                # AI分析部分
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "AI 分析结果"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": "核心动作要点"}}]
                    }
                }
            ]
            
            # 添加核心动作要点
            for action in ai_analysis["核心动作要点"]:
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": action}}]
                    }
                })
            
            # 如果有字幕，添加折叠的字幕内容
            if content_text:
                children.extend([
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "完整字幕"}}],
                            "is_toggleable": True,
                            "children": [
                                {
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [{"type": "text", "text": {"content": content_text[:2000]}}]
                                    }
                                }
                            ]
                        }
                    }
                ])
                
                # 如果字幕太长，分块添加
                if len(content_text) > 2000:
                    for i in range(2000, len(content_text), 2000):
                        children[-1]["heading_2"]["children"].append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": content_text[i:i+2000]}}]
                            }
                        })
            
            # 添加页面内容
            notion.blocks.children.append(
                block_id=page_id,
                children=children
            )
        
        print(f"✅ 成功更新页面: {video_info['title']}")
        return True
    except Exception as e:
        print(f"❌ 更新页面出错: {e}")
        return False


def process_existing_video(video_item: Dict) -> bool:
    """处理已存在的视频，添加AI分析"""
    page_id = video_item["page_id"]
    bvid = video_item["bvid"]
    title = video_item["title"]
    
    print(f"\n处理视频: {title} [{bvid}]")
    
    # 1. 获取视频信息
    video_info = get_video_info(bvid)
    if not video_info:
        print(f"❌ 无法获取视频信息")
        return False
    
    # 2. 相关性过滤
    print("🔍 正在判断是否是巴西柔术相关视频...")
    related = is_bjj_related(video_info)
    if not related:
        print("❌ 无关视频，标记为无关")
        # 标记为无关视频
        try:
            notion.pages.update(
                page_id=page_id,
                properties={
                    "状态": {
                        "select": {
                            "name": "无关视频"
                        }
                    }
                }
            )
            print("✅ 已标记为无关视频")
        except Exception as e:
            print(f"❌ 标记失败: {e}")
        return False
    print("✅ 是相关视频")
    
    # 3. 获取字幕或简介
    subtitle = get_video_cc_subtitle(bvid, video_info["cid"])
    if subtitle:
        content_text = subtitle
        print("✅ 成功获取CC字幕")
    else:
        content_text = f"标题: {video_info['title']}\n简介: {video_info['desc']}"
        print("ℹ️  无CC字幕，使用标题和简介")
    
    # 4. AI分析内容
    print("🤖 正在AI分析内容...")
    ai_analysis = analyze_content_with_ai(content_text)
    if not ai_analysis:
        print("❌ AI分析失败")
        return False
    
    print(f"🏷️  技术分类: {ai_analysis['技术分类']}")
    print(f"📝 核心动作要点: {ai_analysis['核心动作要点']}")
    
    # 5. 更新Notion页面
    success = update_notion_page(page_id, ai_analysis, content_text, video_info, related)
    
    return success


def main():
    print("=" * 60)
    print("批量AI分析工具 - 为已有视频添加技术分类和动作要点")
    print("=" * 60)
    
    # 获取未分析的视频
    videos = get_unanalyzed_videos()
    print(f"发现 {len(videos)} 个未分析的视频")
    
    if not videos:
        print("✅ 所有视频都已经分析完成")
        return
    
    # 处理视频，每次处理5个避免API超限
    processed = 0
    for i, video in enumerate(videos):
        if process_existing_video(video):
            processed += 1
        # 每处理5个休息一下
        if (i + 1) % 5 == 0:
            print(f"\n⏳ 已处理 {i+1} 个，休息3秒...")
            import time
            time.sleep(3)
    
    print(f"\n🎉 处理完成！共成功分析 {processed} 个视频")


if __name__ == "__main__":
    main()
