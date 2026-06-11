from dotenv import load_dotenv
load_dotenv()
import os
from notion_client import Client

# 测试Notion连接
print("测试Notion连接...")
client = Client(auth=os.getenv('NOTION_API_TOKEN'))
try:
    # 先尝试获取数据库信息
    db = client.databases.retrieve(os.getenv('NOTION_DATABASE_ID'))
    print("✅ 数据库连接成功！")
    print("数据库名称:", db['title'][0]['plain_text'])
    print("\n属性列表:")
    for name, prop in db['properties'].items():
        print(f"  - {name}: {prop['type']}")
except Exception as e:
    print("❌ 连接失败:", str(e))
