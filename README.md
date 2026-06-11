# B站巴西柔术视频自动抓取与Notion同步工具

这个工具可以自动抓取B站上最新发布的巴西柔术视频，使用AI分析视频内容，然后同步到Notion数据库中。同时支持手动添加视频条目，自动补全信息。

## 功能特性

1. **自动抓取**：自动搜索B站最新发布的巴西柔术视频
2. **智能排重**：自动跳过已经在Notion中存在的视频
3. **字幕提取**：自动获取视频CC字幕，没有字幕则使用标题+简介
4. **AI分析**：使用大模型分析视频内容，提取技术位置、意图和核心动作要点
5. **Notion同步**：自动将视频信息和分析结果写入Notion数据库
6. **手动兼容**：支持手动在Notion中添加BVID，脚本会自动处理未完成的条目

## 前置要求

### 1. Notion 配置

首先需要创建一个Notion数据库，并准备好集成Token：

#### 数据库属性配置

你的Notion数据库需要包含以下属性：

| 属性名   | 类型         | 说明                     |
|----------|--------------|--------------------------|
| Name     | 标题         | 视频标题                 |
| BVID     | 文本         | B站视频ID（以BV开头）    |
| UP主     | 文本         | 视频上传者名称           |
| Position | 文本         | AI分析出的技术位置       |
| Intention| 文本         | AI分析出的技术意图       |
| 发布日期 | 日期         | 视频发布日期             |
| Status   | 单选         | 处理状态（"已处理"）     |
| Source   | 单选（可选） | 视频来源（如"YouTube 搬运"） |

#### Notion 集成配置

1. 访问 [Notion Developers](https://www.notion.so/my-integrations) 创建新的集成
2. 复制生成的Internal Integration Token
3. 打开你的Notion数据库页面，点击右上角"Share"，将刚才创建的集成添加为协作者
4. 复制数据库ID（从页面URL中获取，URL格式：https://www.notion.so/{workspace}/{database_id}?v=...）

### 2. 环境配置

1. Python 3.8+
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

### 3. 环境变量配置

复制 `.env.example` 为 `.env`，然后填写相关配置：

```env
# Notion 配置
NOTION_API_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_notion_database_id

# B站API配置（不需要认证，公开接口）
BILIBILI_SEARCH_KEYWORD=巴西柔术

# 大模型配置（支持OpenAI兼容接口）
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
```

如果使用其他OpenAI兼容的大模型服务（如DeepSeek、Moonshot等），只需要修改`OPENAI_BASE_URL`和`OPENAI_MODEL`即可。

## 使用方法

### 1. 自动运行

直接运行脚本即可：

```bash
python main.py
```

脚本会自动执行以下流程：
1. 扫描Notion中待处理的手动添加条目（Status为空或缺少Position数据）
2. 自动处理这些条目，获取视频信息、AI分析、补全Notion页面
3. 搜索B站最新的巴西柔术视频
4. 排重后处理新视频，写入Notion数据库

### 2. 手动添加视频

如果你从YouTube、视频号或其他平台找到了好的视频，可以：

1. 下载并上传到你的B站账号
2. 在Notion数据库中手动新建一行
3. 填入`Name`和`BVID`，将`Source`选为"YouTube 搬运"（可选）
4. 下次运行脚本时，会自动识别这些待处理条目，自动补全所有信息

### 3. 定时运行（可选）

可以使用cron（Linux/macOS）或任务计划程序（Windows）设置定时运行，例如每天运行一次：

```bash
# 每天0点运行
0 0 * * * cd /path/to/project && python main.py
```

## 项目结构

```
.
├── main.py              # 主程序文件
├── requirements.txt     # Python依赖
├── .env.example         # 环境变量模板
├── .env                 # 你的私有配置（不会被git提交）
└── README.md            # 说明文档
```

## 注意事项

1. B站API是公开接口，不需要认证，但调用频率不要太高，避免被限流
2. Notion API有速率限制，脚本会自动处理，但大量数据时可能需要较长时间
3. AI分析使用大模型，会产生一定的费用，请根据需要控制处理数量
4. 视频字幕和简介可能很长，脚本会自动截断以适应Notion的长度限制
5. 首次运行时可能会处理大量视频，建议先测试少量数据

## 常见问题

### Q: 运行时提示Notion API错误
A: 请检查你的NOTION_API_TOKEN和NOTION_DATABASE_ID是否正确，并且集成已经被添加到数据库的协作者中。

### Q: 无法获取B站视频信息
A: 请检查网络连接，B站API可能会有地区限制或反爬策略，如果持续失败，可以尝试更换User-Agent。

### Q: AI分析结果不准确
A: 可以尝试更换更强大的模型（如gpt-4o），或者调整main.py中的prompt提示词，使其更符合你的需求。

### Q: 如何修改搜索关键词？
A: 修改.env文件中的BILIBILI_SEARCH_KEYWORD即可，支持任意关键词。
