# Content Digest - 技术方案文档

## 一、产品定位

个人内容聚合摘要工具：自动获取多平台订阅内容（Substack、YouTube、Spotify 播客），生成结构化精华摘要，每日早晨通过邮件推送 + Web 详情页交付。

---

## 二、核心功能

| 功能 | 描述 |
|------|------|
| 内容获取 | 定时抓取 RSS/API，下载播客音频 |
| 音频转录 | ASR 转录播客音频为文字（含说话人分离） |
| 智能摘要 | LLM 生成结构化摘要（核心论点 + 支撑要点 + 结论 + 时间戳） |
| 邮件推送 | 每日早晨发送精美 HTML 邮件 |
| Web 阅读 | 详情页支持时间戳跳转、收藏标记 |
| 订阅管理 | Web 后台手动添加/删除 RSS/URL |

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        定时调度 (Cron)                            │
│                    每日 02:00 AM 触发                             │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     内容获取层 (Fetcher)                          │
│                                                                   │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐     │
│  │ Substack │  │   YouTube    │  │    Spotify Podcasts    │     │
│  │ RSS 解析 │  │ Data API +   │  │  Podcast Index 搜索    │     │
│  │          │  │ 字幕获取     │  │  RSS 下载 + 音频获取   │     │
│  └──────────┘  └──────────────┘  └────────────────────────┘     │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     转录层 (Transcriber)                          │
│                                                                   │
│  Whisper (large-v3) + pyannote-audio (Speaker Diarization)       │
│  仅处理音频内容（播客）                                            │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     摘要层 (Summarizer)                           │
│                                                                   │
│  LLM API (OpenAI 兼容, ai-coding-ali.deeproute.cn/v1)            │
│  模型: glm-5.1 / qwen3.6-plus                                    │
│  输出: 结构化摘要 + 时间戳标注                                     │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     交付层 (Delivery)                             │
│                                                                   │
│  ┌─────────────────┐       ┌──────────────────────────────┐     │
│  │  邮件推送        │       │  Web 应用 (FastAPI + React)   │     │
│  │  SMTP 自发自收   │       │  阅读/收藏/时间戳跳转         │     │
│  └─────────────────┘       └──────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     存储层 (Storage)                              │
│                                                                   │
│  SQLite (元数据 + 摘要)  /  本地文件系统 (临时音频)               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、技术栈

| 层 | 技术选型 | 理由 |
|----|---------|------|
| 语言 | Python 3.11+ | 生态最丰富（feedparser, yt-dlp, openai, whisper） |
| Web 框架 | FastAPI | 轻量、async 友好、API + 前端一体 |
| 前端 | React (Vite) | SPA 阅读体验好，支持 PWA |
| 数据库 | SQLite | 单用户场景无需重量级 DB |
| ASR | faster-whisper + pyannote | 本地推理，零 API 成本 |
| LLM | OpenAI 兼容 API | 接入公司 AI 网关 |
| 定时 | APScheduler / systemd timer | 简单可靠 |
| 邮件 | smtplib (Python 标准库) | 自发自收，无额外依赖 |
| 部署 | Docker Compose | 一键部署，含 GPU 支持 |

---

## 五、数据模型

```python
# 订阅源
class Source:
    id: int
    name: str                    # 订阅名称
    platform: str                # substack / youtube / podcast
    url: str                     # RSS URL / YouTube channel URL
    rss_url: str | None          # 解析后的 RSS 地址
    active: bool
    created_at: datetime

# 内容条目
class Entry:
    id: int
    source_id: int
    title: str
    url: str                     # 原始内容链接
    published_at: datetime
    content_type: str            # article / video / podcast
    raw_text: str | None         # 原文/转录文本
    status: str                  # pending / transcribing / summarizing / done / failed
    created_at: datetime

# 摘要
class Summary:
    id: int
    entry_id: int
    thesis: str                  # 核心论点（1-2 句话）
    key_points: list[dict]       # [{speaker, text, timestamp_start, timestamp_end}]
    conclusion: str              # 一句话结论
    word_count: int              # 摘要总字数
    created_at: datetime

# 收藏
class Bookmark:
    id: int
    entry_id: int
    created_at: datetime

# 每日摘要
class DailyDigest:
    id: int
    date: date
    entry_ids: list[int]
    email_sent: bool
    created_at: datetime
```

---

## 六、核心流程

### 6.1 每日批处理流程

```
02:00 - 触发定时任务
  │
  ├── 1. 遍历所有活跃 Source，检查 RSS 是否有新条目
  │      - 对比 published_at 过滤已处理的
  │      - 新条目写入 Entry 表 (status=pending)
  │
  ├── 2. 按 content_type 分流处理
  │      ├── article: 直接提取正文 → raw_text
  │      ├── video: 获取 YouTube 字幕 → raw_text
  │      └── podcast: 下载音频 → Whisper 转录 → raw_text
  │
  ├── 3. 对每个有 raw_text 的 Entry 调用 LLM 生成摘要
  │      - 使用结构化输出 prompt
  │      - 播客/视频：标注时间戳
  │      - 文章：标注段落位置
  │
  ├── 4. 生成 DailyDigest，汇总当日所有摘要
  │
  └── 5. 发送邮件 (07:00)
         - HTML 模板，包含简版摘要
         - 每条附 "查看详情" Web 链接
```

### 6.2 摘要生成 Prompt 策略

```
你是一个专业的内容摘要助手。请为以下内容生成结构化摘要。

要求：
1. 核心论点：用 1-2 句话概括作者/嘉宾的核心主张
2. 关键要点：提取 3-5 个最有价值的要点，每个要点：
   - 一句话概括
   - 标注对应的时间戳（播客/视频）或段落位置（文章）
3. 结论/行动项：这个内容对读者最大的启发或可采取的行动
4. 如果是访谈类内容，请标注每个要点是谁说的

输出 JSON 格式：
{
  "thesis": "...",
  "key_points": [
    {"speaker": "...", "text": "...", "timestamp": "12:34"}
  ],
  "conclusion": "...",
  "tags": ["topic1", "topic2"]
}
```

---

## 七、各平台接入方案

### 7.1 Substack

- **获取方式**：每个 Substack 都有标准 RSS `https://{name}.substack.com/feed`
- **内容提取**：RSS entry 的 `content:encoded` 字段包含全文 HTML，用 BeautifulSoup 提取纯文本
- **时间戳**：N/A（文章类用段落编号定位）
- **难度**：⭐ 低

### 7.2 YouTube

- **获取方式**：YouTube RSS feed `https://www.youtube.com/feeds/videos.xml?channel_id={id}`（免 API Key）
- **字幕获取**：`youtube-transcript-api` 库，优先手动字幕，fallback 自动生成字幕
- **时间戳**：字幕自带精确时间戳
- **备选**：YouTube Data API v3（需要 API Key，配额 10,000 单位/天）
- **难度**：⭐⭐ 中

### 7.3 Spotify / 英文播客

- **搜索 RSS**：通过 Podcast Index API 按播客名称搜索 RSS 地址
- **音频下载**：从 RSS enclosure 获取音频文件 URL 直接下载
- **转录**：faster-whisper (large-v3) 本地转录
- **说话人分离**：pyannote-audio 区分主持人/嘉宾
- **时间戳**：Whisper 输出自带 word-level timestamps
- **难度**：⭐⭐⭐ 高（ASR + Diarization 链路）

---

## 八、LLM API 配置

```python
LLM_CONFIG = {
    "base_url": "https://ai-coding-ali.deeproute.cn/v1",
    "api_key": "${ANTHROPIC_AUTH_TOKEN}",  # 从环境变量读取
    "model": "glm-5.1",                   # 默认模型
    "timeout": 120,
    "max_tokens": 2000,
}
```

支持的模型（按需切换）：
- `glm-5.1`：通用推理，默认选择
- `qwen3.6-plus`：备选，较强的中英文能力
- `kimi-k2.5`：支持图片理解（如需分析视频截图）

---

## 九、邮件模板设计

每日邮件结构：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📬 Your Daily Content Digest
   {date} · {N} new items
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─ 🎙️ Podcast ─────────────────┐
│ {podcast_title}                │
│ 💡 {thesis}                    │
│ • {key_point_1}               │
│ • {key_point_2}               │
│ → View full summary           │
└───────────────────────────────┘

┌─ 📝 Article ─────────────────┐
│ {article_title}                │
│ 💡 {thesis}                    │
│ • {key_point_1}               │
│ • {key_point_2}               │
│ → View full summary           │
└───────────────────────────────┘

┌─ 🎬 Video ───────────────────┐
│ {video_title}                  │
│ 💡 {thesis}                    │
│ • {key_point_1}               │
│ • {key_point_2}               │
│ → View full summary           │
└───────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Manage subscriptions: {web_url}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 十、Web 页面设计

| 页面 | 路由 | 功能 |
|------|------|------|
| 每日摘要 | `/` | 按日期分组的摘要卡片列表 |
| 日期详情 | `/digest/{date}` | 某天的所有摘要 |
| 内容详情 | `/entry/{id}` | 完整摘要 + 时间戳跳转 + 收藏 |
| 收藏列表 | `/bookmarks` | 已收藏内容 |
| 订阅管理 | `/sources` | 增删改查订阅源 |

### Web 详情页核心交互

- **时间戳跳转**：播客/视频的每个要点旁有时间戳按钮，点击跳转到原始内容对应位置
  - YouTube：`https://youtu.be/{id}?t={seconds}`
  - 播客：内嵌音频播放器 seek 到对应位置
- **收藏标记**：点击星标收藏，收藏后出现在 `/bookmarks`
- **原文链接**：每条摘要顶部有"查看原文"按钮

---

## 十一、部署方案

### Docker Compose

```yaml
version: "3.8"
services:
  app:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
    environment:
      - ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN}
      - SMTP_HOST=${SMTP_HOST}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASS=${SMTP_PASS}
      - RECIPIENT_EMAIL=${RECIPIENT_EMAIL}
      - WEB_BASE_URL=${WEB_BASE_URL}
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]   # 可选：本地 Whisper 需要
```

### 服务器最低配置

| 场景 | CPU | 内存 | GPU | 磁盘 |
|------|-----|------|-----|------|
| 无本地 ASR | 2 核 | 4 GB | 无 | 20 GB |
| 有本地 ASR | 4 核 | 8 GB | 1× (6GB+ VRAM) | 50 GB |

---

## 十二、开发计划

### Phase 1：核心链路（3-5 天）

- [x] 项目骨架搭建（FastAPI + SQLite + 数据模型）
- [x] Substack RSS 解析 + 全文提取
- [x] YouTube RSS + 字幕获取
- [x] LLM 摘要生成（结构化 JSON 输出）
- [x] 邮件 HTML 模板 + SMTP 发送
- [x] APScheduler 定时调度
- [x] 基本的 CLI 管理命令（添加订阅源、手动触发）
- [x] Web API（FastAPI REST endpoints）
- [ ] **配置 LLM API token 并验证摘要生成**
- [ ] **配置 SMTP 并验证邮件发送**

### Phase 2：播客链路（3-5 天）

- [ ] Podcast Index API 集成（按名称搜索 RSS）
- [ ] 播客音频下载管理（临时存储 + 清理）
- [ ] faster-whisper 转录集成
- [ ] pyannote-audio 说话人分离
- [ ] 播客摘要时间戳对齐

### Phase 3：Web 前端（2-3 天）

- [x] React + Vite 项目搭建
- [x] 每日摘要列表页（卡片式布局，按日期分组）
- [x] 摘要详情页（时间戳跳转 + 收藏）
- [x] 收藏功能
- [x] 订阅源管理页（CRUD）
- [x] 响应式设计（适配手机阅读）
- [x] SPA 路由 + FastAPI 静态文件集成

### Phase 4：优化迭代（持续）

- [ ] Prompt 调优（提高摘要质量和一致性）
- [ ] 失败重试 + 错误通知
- [ ] 内容去重（同一播客在不同平台）
- [ ] 并发处理（多条目并行摘要）
- [ ] 可选：PWA 支持（离线阅读）

---

## 十三、前置准备清单

| 项目 | 说明 | 优先级 |
|------|------|--------|
| SMTP 邮箱配置 | Gmail 需开启应用专用密码；Outlook 需开启 SMTP | P0 |
| 公司服务器 | Linux + Docker，有 GPU 更佳 | P0 |
| 初始订阅列表 | 你想订阅的 Substack/YouTube 频道/播客名称 | P1 |
| YouTube API Key | 可选，用 RSS 可以不需要 | P2 |
| Podcast Index API Key | 免费申请：podcastindex.org/signup | P1 |

---

## 十四、风险与缓解

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| YouTube 字幕不可用 | 低 | 无法摘要该视频 | 标记为"无字幕"，保留链接 |
| 播客无 RSS | 低 | 个别播客无法接入 | Podcast Index 覆盖率很高；极少数放弃 |
| ASR 转录质量差 | 中 | 摘要信息失真 | large-v3 对英文准确率 >95%；重口音可标记 |
| LLM 摘要幻觉 | 低 | 生成不存在的信息 | Prompt 约束 + 保留原文链接验证 |
| AI 网关不稳定 | 低 | 当日摘要延迟 | 重试 3 次 + 备选模型 fallback |
| RSS 格式不标准 | 中 | 解析失败 | feedparser 容错能力强；异常条目跳过不阻塞 |

---

## 十五、未来可扩展方向

- **更多平台**：小宇宙、Apple Podcasts、Medium、Twitter/X threads
- **个性化排序**：根据阅读历史和收藏，给内容打优先级分
- **多语言支持**：中文播客接入（FunASR 替代 Whisper）
- **协作分享**：将某条摘要分享给朋友
- **语音播报**：TTS 将摘要读给你听（通勤场景）
- **知识图谱**：跨内容源的主题关联和回溯
