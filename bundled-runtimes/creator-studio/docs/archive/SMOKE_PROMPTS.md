# Dasheng SOP 每日首跑自检提示词

## 1) 全链路最小自检（推荐）

```
使用 dasheng-sop-orchestrator 执行一次最小自检：
1) 检查环境变量与路径可访问；
2) 按 intake -> brief -> draft -> material -> rewrite -> publish -> postmortem 输出每阶段应交付文件清单；
3) 不生成正式内容，只生成“待执行队列 + 风险项 + 阻塞项”。
输出到今日目录的 smoke_report.md。
```

## 2) 发布前视频补充自检

```
使用 dasheng-stage-publish-video 做发布前补充自检：
1) 检查 finance-motion-8787 可执行；
2) 检查 CSV/表格输入是否可映射到 scene；
3) 检查改写稿是否可提炼 motion 脚本。
输出 publish_video_smoke.md，列出失败点与修复建议。
```

## 3) 飞书交付链路自检

```
检查飞书交付链路：
1) 能否在共享目录下创建文档；
2) 能否将文档链接发送到群；
3) 能否在文档中插入图片与图表。
只输出链路状态，不写正文。
```
