# AVIP·Studio — TikTok 数字人虚拟 IP 批量生产工作室

面向北美市场的 TikTok 批量短视频生产应用：**虚拟IP人设管理 → 批量剧本生成（钩子×格式×LLM）→ 数字人语音/形象生成（HeyGen/D-ID/Synthesia）→ 自动后期（片头钩子卡+片尾关注卡）→ 内容日历+发布清单**。附内置模拟模式（mock），零 API 成本即可跑通全流程。


## 一键部署为「永久在线网站」（输入网址即用，不装本地）

不想本地跑/不想维护服务器？把代码推到 GitHub（或直接连仓库），用 PaaS 平台一键部署成属于你的固定网址。

**选择一家平台（任选其一，均支持 Dockerfile）：**

| 平台 | 说明 |
|---|---|
| [Render](https://render.com) | 本项目已附 `render.yaml`；注册 → New → Import Blueprint → 选仓库 → Deploy 即得 `https://<name>.onrender.com` |
| [Railway](https://railway.app) | 已附 `railway.json`；New Project → Deploy from GitHub Repo → 自动容器化 |
| [Zeabur](https://zeabur.com) | 国内友好；创建项目 → 关联仓库 → 自动识别 Dockerfile |

**部署后要做的极简配置（平台面板 → 环境变量）：**
```
FAL_API_KEY=你的key:secret      （必填，需在设置里选 fal.ai 托管数字人）
PROVIDER=fal
DATA_DIR=/data                   （render 已配磁盘卷 /data，持久保存数据）
```
然后浏览器打开平台给你的固定网址 → 上传照片 → 生成第一条视频。全流程与本地版完全一致，网址永久可访问（平台免费额度可能有休眠/资源限制，需常驻可用可考虑小额付费档，以各平台当前价格为准）。

> 说明：TTS 配音默认用应用内置（HeyGen 免费示例 Voice ID，或你在设置里配 ElevenLabs Key）；fal.ai 出片需你的 FAL_API_KEY。这些 Key 都填在**平台环境变量/应用设置页**，不进代码仓库。

## 架构

```
┌────────────── 前端看板 (frontend/index.html 单文件SPA) ──────────────┐
│  概览 | 虚拟IP | 脚本工坊 | 批量生产 | 发布中心 | 设置                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ REST /api/*
┌──────────────────────────────▼──────────────────────────────────────┐
│  server.py  FastAPI + SQLite(studio.db)                              │
│   - 虚拟IP CRUD        - 脚本生成(模板 + OpenAI兼容LLM)               │
│   - 批量入队/任务       - 内容日历(美东时段自动排期)                  │
│   - CSV发布清单导出     - 统计/成本估算                               │
└──────────────────────────────┬──────────────────────────────────────┘
             engine/ 后台工人线程 (串行消费队列)
   ┌───────────┬───────────┬────────────┬─────────────┐
   │generator  │ providers  │  assembly  │   queue     │
   │ 钩子/正文  │ HeyGen     │ 片头/片尾卡 │  任务状态机  │
   │ 标签/排期  │ D-ID       │ 拼接       │  进度/重试   │
   │ LLM 接入  │ Synthesia  │            │             │
   │           │ Mock(ffmpeg)│           │             │
   └───────────┴───────────┴────────────┴─────────────┘
                             ↓ generated/*.mp4 (1080x1920 竖版)
```

## 快速开始

```bash
pip install -r requirements.txt        # fastapi uvicorn requests
python server.py                       # http://localhost:8000
```

打开 `http://localhost:8000` 即为控制台。默认配置为 **mock 模式**（本地生成竖版动画标题卡视频，无任何成本）：
1. 「虚拟IP」新建或沿用预置形象（Alex Carter 健身 / Jake Sterling 财经）
2. 「脚本工坊」输入主题 → 选格式与钩子风格 → 生成（可勾选 LLM）
3. 「批量生产」勾选素材 → 开始批量生产 → 实时看进度 → 预览/下载成片
4. 「发布中心」查看美东时段自动排期 → 导出 CSV 发布清单

## 接入真实数字人（推荐 HeyGen）

1. 注册 [HeyGen](https://www.heygen.com) → 创建/购买形象或用官方预设 Avatar ID
2. 生成 API Key（Settings → API → API token），充值按量额度（起步 $5）
3. 环境变量或看板「设置」填入：

```bash
PROVIDER=heygen
HEYGEN_API_KEY=eyJ...
HEYGEN_AVATAR_ID=<你的形象ID>          # 测试可用官方 "Adopt-an-Avatar"
HEYGEN_VOICE_ID=V7qG2k3p1s5x9jU0zM6e  # 官方示例美式男声
# 可选
LLM_BASE_URL=https://api.deepseek.com/v1   # OpenAI兼容LLM生成剧本
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

切换后重新「批量生产」，流水线自动变为：**HeyGen TTS 配音 → 数字人视频生成 → 片头钩子卡+片尾关注卡拼装**；生成成本实时估算显示。

> 其他提供商：`PROVIDER=did`（需形象图片 URL）、`PROVIDER=synthesia`（需全量 Key）。见 `engine/providers.py`。

## fal.ai 托管数字人（推荐 · 零部署 · 按量付费）

不碰部署：照片 + TTS 音频直接提交 fal.ai 官方 serverless 推理（`fal-ai/sadtalker` / `fal-ai/live-portrait`），返回口播视频。适配器内置：本地图片/音频自动转 base64 data URI、queue 提交与轮询（`Authorization: Key <FAL_KEY>`）、竖版化到 1080x1920。

**接入**：fal.ai 注册获取 API Key（`key:secret`）→ 设置页选 **fal.ai 托管数字人**、填 Key → 虚拟IP上传照片 → 批量生产即走「TTS 配音 → fal.ai 推理 → 竖版化+片头尾拼接」。引擎未配置/未带音频时，任务会明确报错提示。

**计费**：按模型输出计费、随用随付，无订阅。具体单价以 fal 控制台实际账单为准（[fal.ai/pricing](https://fal.ai/pricing) 与各模型页）。官方模型页与 SDK：[fal-ai/sadtalker](https://fal.ai/models/fal-ai/sadtalker/api)。输出分辨率 256/512px，竖版化后清晰度有限——追求高清可换支持更高分辨率的端点。

## 本地开源引擎（LivePortrait · 自建备选 · 零API费）

不依赖付费服务：上传一张照片作为虚拟 IP 形象，由本机/自有 GPU 机器上的 **LivePortrait**（快手 KlingAIResearch 开源）生成口播视频。

**部署引擎（需要 GPU，推荐 12GB+ 显存；无 GPU 可租云 GPU 跑 worker）**

```bash
# 1) 克隆并安装（约 2-6GB 权重）
git clone https://github.com/KlingAIResearch/LivePortrait
cd LivePortrait && pip install -r requirements.txt
# 下载预训练权重（HuggingFace，见仓库说明）

# 2) 启动推理 worker（HTTP 服务，默认端口 8765）
python3 liveportrait_worker.py --port 8765
# 仓库自带推理脚本；单独启动一个极简 FastAPI worker 提供
#   POST /generate {photo_url, text|audio_url} → {video_url}
```

**接入本应用**

1. 看板「虚拟 IP」→ 上传照片 → 自动写入 `avatar_url`
2. 「设置」→ 提供商选 **LivePortrait 本地引擎** → 填写引擎地址（如 `http://127.0.0.1:8765`，远程 GPU 填公网地址）
3. 保存后「批量生产」即走：TTS 配音 → 照片+音频 → LivePortrait → 片头/片尾拼接

**说明**：适配器会先做健康检查（`/health`）与照片校验；引擎未启动时任务会明确报错。TTS 优先用引擎侧生成音频后上传（支持 text 或 audio 两种输入）。竖版化/字幕/片头片尾由本应用 ffmpeg 完成，适配器已内置。

成本：仅 GPU 电费/租卡费（消费级卡约 ¥1-3/小时）。效果：口型+头部微动真实；幅度与表情丰富度稍逊 HeyGen 棚拍形象。

> 其他同样可用：SadTalker、EchoMimic、Hallo2、MuseTalk 等，适配器模式相同，换 worker 即可。

## 发布通道（TikTok 官方 API 现状 2026）

| 方案 | 成本 | 说明 |
|---|---|---|
| **A. Content Posting API** | 官方免费 | 公开发布需 App 审核（2–6 周；提交演示视频+隐私政策）。审核前仅沙箱私密可见。上限约 **25 条/天/账号**、**6 请求/分钟**、access token 24h |
| **B. 已过审第三方** | 约 $29/月起 | Blotato、Ayrshare 等已过审，一个接口接 TikTok+多平台，可跳过自有审核，适合矩阵 |
| **C. 人工/半自动队列** | 0 | 导出 CSV 清单 + 视频下载链接，按日历时段发布，起步最快 |

**合规红线**：TikTok 要求 AI 生成/合成内容显著披露（如字幕 `AI-generated`）。数字人口播+AI文案属于合成内容，务必标注，否则有隐形限流/下架风险。审核演示视频可在沙箱模式录制（帖子强制私密，但录屏可通过审核）。

## 成本参照（HeyGen 官方 2026 按量计费）

| 项 | 单价 |
|---|---|
| Avatar III 引擎 720p/1080p（照片/分身/棚拍同价） | **$1.00 / 分钟** |
| Avatar IV 引擎（Photo/Digital Twin/Studio） | $3.00–4.00 / 分钟 |
| TTS（Speech Starfish） | $0.04 / 分钟 |
| API 并发 | 10 个任务 |
| 计费 | 按秒计费，$1 购买 ≈ 1 分钟 1080p |

数据来源：[HeyGen API Pricing](https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained)、[HeyGen](https://www.heygen.com/api-pricing)；TikTok 限制见 [developers.tiktok.com](https://developers.tiktok.com/doc/content-sharing-guidelines/)。

## API 摘要

```
GET  /api/avips · POST /api/avips
POST /api/scripts/generate         # {avip_id, topic, format, hook_style, use_llm}
GET  /api/scripts · POST /api/scripts · DELETE /api/scripts/{id}
POST /api/batch                    # {avip_id, items:[{script_id}|{topic,...}]}
GET  /api/jobs                     # 生产队列
POST /api/jobs/{id}/retry|cancel
GET  /api/jobs/{id}/file           # 成片视频
GET  /api/calendar · GET /api/export.csv
GET  /api/settings · POST /api/settings · POST /api/settings/test
GET  /api/stats · GET /api/rates
```

## 路线图建议
- 视频号矩阵：多账号管理 + 每账号专属 IP/风格
- 评论/热梗反哺选题（TikTok Display API 读趋势，官方审核或第三方提供）
- 一键发布对接（方案 B 已过审服务）
- LLM 批次润色 + A/B 钩子测试（同一主题 5 钩子生成 5 版，按数据回流选优）
- 数据分析回流：播放/完播率 → 自动调整钩子与话题标签
