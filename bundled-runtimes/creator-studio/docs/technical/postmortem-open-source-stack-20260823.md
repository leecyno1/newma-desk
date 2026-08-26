# Newma Creator Studio 复盘开源技术储备

更新时间：2026-08-23

## 结论

复盘阶段不应再造一套“大而全”的社媒后台。Newma 继续负责工作流、交付物、审核和指标归一；外部项目只负责三类深模块：平台读数、竞品采集、评论分析。

## 节点与采用方案

| 复盘节点 | 首选 | 补充 | 接入方式 |
| --- | --- | --- | --- |
| 数据回收 | OpenCLI + wechatpy | Postiz、Mixpost、官方 YouTube API | 读取平台真实数据，输出 `performance_dataset` 与截图；Postiz/Mixpost 保持完整服务，通过薄 Adapter 导出 |
| 同题竞品对比 | MediaCrawler + minet + yt-dlp | 4CAT + Zeeschuimer、XHS-Downloader、twscrape、TikTok-Api | 国内平台用隔离 Worker，公开视频用 CLI；全部输出统一 `competitor_dataset` |
| 效果归因 | Newma 归因规则 | BERTopic + PyABSA；数据积累后启用 DoWhy | 主题和分方面意见只做分析依赖；单次作品禁止做因果结论 |
| 知识回写 | Newma Learning Gate | 无 | 外部项目不得直接修改 DNA、IP 模板或发布策略 |

## 重点项目

| 项目 | 适用价值 | 决策 |
| --- | --- | --- |
| [Postiz](https://github.com/gitroomhq/postiz-app) | 多平台发布和 Analytics，可复用账号与作品指标后台 | 已保留；补充 Postmortem 路由，待 Analytics 导出 Adapter |
| [Mixpost](https://github.com/inovector/mixpost) | 各平台 Analytics 与受众洞察 | 候选；完整服务接入，不拆源码 |
| [wechatpy](https://github.com/wechatpy/wechatpy) | 公众号阅读、分享和用户数据的官方接口封装 | 直接采用 datacube Client |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 小红书、抖音、快手、B站、微博、贴吧、知乎的关键词、作品、作者和评论 | 国内竞品首选；作为隔离采集 Worker |
| [4CAT](https://github.com/digitalmethodsinitiative/4cat) | TikTok、Instagram、X、小红书、YouTube 等数据导入与分析 | 竞品对比首选；用数据集 Handoff 接入 |
| [Zeeschuimer](https://github.com/digitalmethodsinitiative/zeeschuimer) | 浏览器可见社媒数据采集 | 只作为 4CAT 的采集伴侣 |
| [minet](https://github.com/medialab/minet) | YouTube 搜索、网页与社媒数据采集 CLI | 低耦合竞品搜索 Adapter |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 视频元数据、字幕、封面、评论和样片 | 直接采用 JSON CLI；不冒充官方 Analytics |
| [XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) | 小红书作品、搜索结果与点赞/收藏/评论字段 | 已保留；补充竞品指标归一 |
| [TikTok-Api](https://github.com/davidteather/TikTok-Api) | TikTok 搜索、作品和评论采集 | 可选 Adapter，必须保留浏览器回退 |
| [twscrape](https://github.com/vladkens/twscrape) | X 搜索、帖子和线程采集 | 可选 Adapter，账号轮换不进入共享状态 |
| [YouTube Operational API](https://github.com/Benjamin-Loison/YouTube-operational-API) | 官方 API 失效时的公开视频数据补充 | 只做后备，官方 YouTube API 始终优先 |
| [BERTopic](https://github.com/MaartenGr/BERTopic) | 评论主题聚类、主题演变、用户问题提炼 | 作为分析依赖嵌入效果归因 |
| [PyABSA](https://github.com/yangheng95/PyABSA) | 按标题、开头、数据、画面和配音提取分方面意见 | 评论归一后使用，中文语料需校准 |
| [DoWhy](https://github.com/py-why/dowhy) | 跨批次实验的因果假设与反驳检验 | 仅在历史样本和对照实验足够后启用 |

## 数据接缝

所有采集器必须统一交付：

- `platform_snapshot`：平台页面或后台截图，作为真实性凭证。
- `performance_dataset`：本账号作品的 1 天、3 天、7 天指标。
- `competitor_dataset`：同题样本、原链接、标题、发布时间、互动和采集时间。
- `comment_dataset`：评论原文、平台、作品、时间和可追溯 ID。

外部项目不得直接写入 DNA 或 IP 模板。只有 `knowledge_writeback` 节点经用户审核后才能回写 Learning。
