#!/usr/bin/env python3
import os
import re
import json
import requests
from dotenv import load_dotenv
from notion_client import Client
from openai import OpenAI
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# 加载环境变量
load_dotenv()

# 配置常量
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
BILIBILI_SEARCH_KEYWORDS = [kw.strip() for kw in os.getenv("BILIBILI_SEARCH_KEYWORD", "巴西柔术").replace("，", ",").split(",") if kw.strip()]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# 初始化客户端
notion = Client(auth=NOTION_API_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


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


def search_bilibili_videos(keyword: str, page_size: int = 30) -> List[Dict]:
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


def create_notion_page(video_info: Dict, ai_analysis: Dict, content_text: str) -> Optional[str]:
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
            "技术分类": {
                "multi_select": [{"name": tag} for tag in ai_analysis["技术分类"]]
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
        
        # 添加核心动作要点到属性和内容
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
        
        for action in ai_analysis["核心动作要点"]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": action}}]
                }
            })
        
        # 视频简介
        children.extend([
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
        ])
        
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


def update_notion_page(page_id: str, ai_analysis: Dict, content_text: str, video_info: Dict = None) -> bool:
    """更新已存在的Notion页面（处理手动添加的条目）"""
    try:
        # 转换时长格式
        duration_str = ""
        if video_info:
            duration_seconds = int(video_info["duration"])
            duration_str = f"{duration_seconds//60}:{duration_seconds%60:02d}"
        
        # 构造更新的属性
        properties = {
            "技术分类": {
                "multi_select": [{"name": tag} for tag in ai_analysis["技术分类"]]
            },
            "状态": {
                "select": {
                    "name": "已处理"
                }
            }
        }
        
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
        
        # 如果有视频信息，补充其他属性
        if video_info:
            properties.update({
                "Title": {
                    "title": [
                        {
                            "text": {
                                "content": video_info["title"]
                            }
                        }
                    ]
                },
                "发布日期": {
                    "date": {
                        "start": datetime.fromtimestamp(video_info["pubdate"]).isoformat()
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
            })
        
        # 构造页面内容
        children = [
            # B站视频嵌入
            {
                "object": "block",
                "type": "embed",
                "embed": {
                    "url": f"https://www.bilibili.com/video/{video_info['bvid']}/"
                }
            } if video_info else {},
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
            } if video_info else {},
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
        
        # 过滤掉空块
        children = [b for b in children if b]
        
        # 添加核心动作要点
        for action in ai_analysis["核心动作要点"]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": action}}]
                }
            })
        
        # 视频简介
        if video_info:
            children.extend([
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
            ])
        
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
        
        # 更新页面属性
        notion.pages.update(
            page_id=page_id,
            properties=properties
        )
        
        # 添加页面内容
        notion.blocks.children.append(
            block_id=page_id,
            children=children
        )
        
        print(f"✅ 成功更新Notion页面: {page_id}")
        return True
    except Exception as e:
        print(f"❌ 更新Notion页面出错: {e}")
        return False


def get_pending_notion_pages() -> List[Tuple[str, str]]:
    """获取Notion中待处理的页面（状态为空或技术分类为空）"""
    pending_pages = []
    
    has_more = True
    next_cursor = None
    
    while has_more:
        response = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            cursor=next_cursor,
            filter={
                "or": [
                    {
                        "property": "状态",
                        "select": {
                            "is_empty": True
                        }
                    },
                    {
                        "property": "技术分类",
                        "multi_select": {
                            "is_empty": True
                        }
                    }
                ]
            }
        )
        
        for page in response["results"]:
            # 获取BV号
            bvid_property = page["properties"].get("BV号", {})
            if bvid_property.get("rich_text"):
                bvid = bvid_property["rich_text"][0]["plain_text"].strip()
                if bvid and bvid.startswith("BV"):
                    pending_pages.append((page["id"], bvid))
        
        has_more = response["has_more"]
        next_cursor = response["next_cursor"]
    
    return pending_pages


def process_single_video(bvid: str, page_id: str = None) -> bool:
    """处理单个视频（支持新建或更新）"""
    print(f"\n开始处理视频: {bvid}")
    
    # 1. 获取视频信息
    video_info = get_video_info(bvid)
    if not video_info:
        print(f"❌ 无法获取视频信息: {bvid}")
        return False
    
    print(f"📹 视频标题: {video_info['title']}")
    print(f"👤 UP主: {video_info['owner']['name']}")
    print(f"⏱️  视频时长: {int(video_info['duration'])//60}:{int(video_info['duration'])%60:02d}")
    
    # 2. 相关性过滤
    print("🔍 正在判断是否是巴西柔术相关视频...")
    if not is_bjj_related(video_info):
        print("❌ 无关视频，跳过")
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
    
    # 5. 写入或更新Notion
    if page_id:
        # 更新现有页面
        success = update_notion_page(page_id, ai_analysis, content_text, video_info)
    else:
        # 创建新页面
        success = create_notion_page(video_info, ai_analysis, content_text) is not None
    
    return success


def main():
    print("=" * 60)
    print("B站巴西柔术视频自动抓取与Notion同步工具（完整版）")
    print("=" * 60)
    
    # 第一步：处理待处理的手动添加条目
    print("\n[步骤1] 扫描Notion中待处理的手动添加条目...")
    pending_pages = get_pending_notion_pages()
    
    if pending_pages:
        print(f"发现 {len(pending_pages)} 个待处理条目")
        for page_id, bvid in pending_pages:
            process_single_video(bvid, page_id)
    else:
        print("✅ 没有待处理的手动条目")
    
    # 第二步：自动搜索新视频
    print("\n[步骤2] 搜索B站最新发布的巴西柔术视频...")
    existing_bvids = get_existing_bvids()
    print(f"当前Notion中已有 {len(existing_bvids)} 个视频")
    
    all_videos = []
    for kw in BILIBILI_SEARCH_KEYWORDS:
        print(f"\n
    正在搜索关键词: {kw}")
        videos = search_bilibili_videos(kw, page_size=30)
        all_videos.extend(videos)
        print(f"关键词 {kw} 搜索到 {len(videos)} 个视频")
# 按BV号去重，避免同一个视频在多个关键词里被搜到
seen_bvids = set()
unique_videos = []
for video in all_videos:
    bvid = video["bvid"]
    if bvid not in seen_bvids:
        seen_bvids.add(bvid)
        unique_videos.append(video)
videos = unique_videos
print(f"
所有关键词共搜索到 {len(all_videos)} 个视频，去重后 {len(videos)} 个")
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
    
    # 处理新视频，最多处理10个
    processed_count = 0
    for i, video in enumerate(new_videos):
        if processed_count >= 10:
            break
        bvid = video["bvid"]
        print(f"\n[{i+1}/{len(new_videos)}] 处理新视频: {bvid}")
        if process_single_video(bvid):
            processed_count += 1
        print(f"已成功处理 {processed_count}/10 个视频")
    
    print("\n🎉 所有处理任务结束")


if __name__ == "__main__":
    main()
