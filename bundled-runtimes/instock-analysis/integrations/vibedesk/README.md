# 旧 VibeDesk 兼容交付物

Newma-Desk 的规范来源已经迁移到 `integrations/newma-desk/`。本目录保留单页 `mod.json` / `module.json` 与旧路径，供尚未支持 Mod Suite 自动发现的安装器使用。

兼容文件与标准 Suite 使用相同的 Level 2 Action 合同：

- `analysis.czsc`
- `analysis.czsc.scan`
- `analysis.rotation`
- `analysis.rotation.experiment`
- `analysis.industry-chain`

`analysis.rotation.supply-chain` 仅作为旧 HTTP Adapter 保留，不再由轮动 Mod 暴露。

Bridge 协议消息名继续使用 `vibedesk:*`，这是 Newma-Desk Bridge Protocol 1.0 的稳定线协议，不代表项目仍依赖旧 Desk 实现。

兼容 Manifest 同步声明轮动发出、CZSC 接收 `security.selected`；产业链研究是独立的 `instock-industry-chain` Mod。事件 Envelope 沿用 Desk 既有规范，BroadcastChannel 只保留给维护诊断。

新的接入、部署与环境变量说明请阅读 `integrations/newma-desk/README.md`。
