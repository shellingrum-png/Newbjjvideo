from dotenv import load_dotenv
load_dotenv()
import os
from notion_client import Client

print("连接数据库...")
client = Client(auth=os.getenv("NOTION_API_TOKEN"))
try:
    db = client.databases.retrieve(os.getenv("NOTION_DATABASE_ID"))
    print("✅ 数据库连接成功")
    print("数据库名称:", db["title"][0]["plain_text"])
    
    print("\n查询数据...")
    response = client.databases.query(database_id=os.getenv("NOTION_DATABASE_ID"), page_size=1)
    print("✅ 查询成功，共有", len(response["results"]), "条数据")
except Exception as e:
    print("❌ 出错:", str(e))
