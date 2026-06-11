#!/usr/bin/env python3
import os
import requests
from dotenv import load_dotenv
from notion_client import Client
from datetime import datetime
from typing import List, Dict, Optional

# 加载环境变量
load_dotenv()

# 配置常量
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
BILIBILI_SEARCH_KEYWORD = os.getenv("BILIBILI_SEARCH_KEYWORD", "巴西柔术")

# 初始化客户端
notion = Client(auth=NOTION_API_TOKEN)


def get_existing_bvids() -> List[str]:
    """从Notion数据库中获取所有已存在的BVID"""
    bvids = []
    has_more = True
    next_cursor = None
    
    while has_more:
        response = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            cursor=next_cursor
        )
        
        for page in response["results"]:
            # 获取BV号属性
            bvid_property = page["properties"].get("BV号", {})
            if bvid_property.get("rich_text"):
                bvid = bvid_property["rich_text"][0]["plain_text"].strip()
                if bvid:
                    bvids.append(bvid)
        
        has_more = response["has_more"]
        next_cursor = response["next_cursor"]
    
    return list(set(bvids))  # 去重


def search_bilibili_videos(keyword: str, page_size: int = 10) -> List[Dict]:
    """调用B站搜索API，获取最新发布的视频"""
    url = "https://api.bilibili.com/x/web-interface/search/all/v2"
    params = {
        "keyword": keyword,
        "search_type": "video",
        "order": "pubdate",  # 按最新发布排序
        "page_size": page_size,
        "page": 1
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data["code"] != 0:
            print(f"B站搜索API请求失败: {data['message']}")
            return []
        
        # 提取视频列表
        for result in data["data"]["result"]:
            if result["result_type"] == "video":
                return result["data"]
        
        return []
    except Exception as e:
        print(f"调用B站搜索API出错: {e}")
        return []


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


def create_notion_page(video_info: Dict, content_text: str) -> Optional[str]:
    """在Notion数据库中创建新页面"""
    try:
        # 转换时长格式 秒 -> 分:秒
        duration_seconds = int(video_info["duration"])
        duration_str = f"{duration_seconds//60}:{duration_seconds%60:02d}"
        
        # 构造属性
        properties = {
            "Title": {
                "title": [
                    {
                        "text": {
                            "content": video_info["title"]
                        }
                    }
                ]
            },
            "BV号": {
                "rich_text": [
                    {
                        "text": {
                            "content": video_info["bvid"]
                        }
                    }
                ]
            },
            "发布日期": {
                "date": {
                    "start": datetime.fromtimestamp(video_info["pubdate"]).isoformat()
                }
            },
            "状态": {
                "select": {
                    "name": "已处理"
                }
            },
            "URL": {
                "url": f"https://www.bilibili.com/video/{video_info['bvid']}/"
            },
            "时长": {
                "rich_text": [
                    {
                        "text": {
                            "content": duration_str
                        }
                    }
                ]
            }
        }
        
        # 构造页面内容
        children = [
            # B站视频嵌入
            {
                "object": "block",
                "type": "embed",
                "embed": {
                    "url": f"https://www.bilibili.com/video/{video_info['bvid']}/"
                }
            },
            # UP主信息
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "UP主: "}},
                        {"type": "text", "text": {"content": video_info["owner"]["name"], "link": {"url": f"https://space.bilibili.com/{video_info['owner']['mid']}"}}}
                    ]
                }
            },
            # 视频简介
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "视频简介"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": video_info["desc"][:2000]}}]
                }
            }
        ]
        
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
        
        # 创建页面
        response = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties=properties,
            children=children
        )
        
        print(f"✅ 成功创建Notion页面: {video_info['title']}")
        return response["id"]
    except Exception as e:
        print(f"❌ 创建Notion页面出错: {e}")
        return None


def process_single_video(bvid: str) -> bool:
    """处理单个视频"""
    print(f"\n开始处理视频: {bvid}")
    
    # 1. 获取视频信息
    video_info = get_video_info(bvid)
    if not video_info:
        print(f"❌ 无法获取视频信息: {bvid}")
        return False
    
    print(f"📹 视频标题: {video_info['title']}")
    print(f"👤 UP主: {video_info['owner']['name']}")
    print(f"⏱️  视频时长: {int(video_info['duration'])//60}:{int(video_info['duration'])%60:02d}")
    
    # 2. 获取字幕
    subtitle = get_video_cc_subtitle(bvid, video_info["cid"])
    if subtitle:
        content_text = subtitle
        print("✅ 成功获取CC字幕")
    else:
        content_text = None
        print("ℹ️  无CC字幕")
    
    # 3. 写入Notion
    success = create_notion_page(video_info, content_text) is not None
    
    return success


def main():
    print("=" * 60)
    print("B站巴西柔术视频自动抓取与Notion同步工具（简化版）")
    print("=" * 60)
    
    # 自动搜索新视频
    print("\n[步骤1] 搜索B站最新发布的巴西柔术视频...")
    existing_bvids = get_existing_bvids()
    print(f"当前Notion中已有 {len(existing_bvids)} 个视频")
    
    videos = search_bilibili_videos(BILIBILI_SEARCH_KEYWORD, page_size=5)
    if not videos:
        print("❌ 未搜索到视频")
        return
    
    print(f"搜索到 {len(videos)} 个视频")
    
    # 排重，只处理新视频
    new_videos = []
    for video in videos:
        bvid = video["bvid"]
        if bvid not in existing_bvids:
            new_videos.append(video)
    
    print(f"其中有 {len(new_videos)} 个新视频需要处理")
    
    # 处理新视频
    for i, video in enumerate(new_videos):
        bvid = video["bvid"]
        print(f"\n[{i+1}/{len(new_videos)}] 处理新视频: {bvid}")
        process_single_video(bvid)
    
    print("\n🎉 所有处理任务结束")


if __name__ == "__main__":
    main()
