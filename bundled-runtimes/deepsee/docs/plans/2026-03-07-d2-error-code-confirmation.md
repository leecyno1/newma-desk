# D2 错误码确认记录（故障分类与归因）

日期：2026-03-07  
阶段：P0 稳定性（D2）  
状态：`in_review`

---

## 1) 错误码格式（冻结建议）

格式：`<DOMAIN>-<TYPE>-<NNN>`

- `DOMAIN`：`SYS/ING/MOD/RTR/RND/EXP/SND/DB/CFG/NET/UI`
- `TYPE`：`TIMEOUT/AUTH/UNAVAILABLE/RATE/DATA/STATE/VALIDATION/DEPENDENCY/UNKNOWN`
- `NNN`：三位流水号（域内递增）

示例：
- `SYS-STATE-001`
- `MOD-TIMEOUT-001`
- `EXP-RENDER-002`

---

## 2) 严重级别（冻结建议）

- `P0`：全局不可用，立即告警
- `P1`：核心功能降级，分钟级告警
- `P2`：局部失败，可降级后继续
- `P3`：体验问题，进入日报

---

## 3) 重试矩阵（冻结建议）

可重试：
- `TIMEOUT/UNAVAILABLE/RATE/NET`

不可重试：
- `AUTH/VALIDATION`

条件重试（1次后人工）：
- `DATA/UNKNOWN`

默认退避：
- `1s -> 3s -> 7s`，最大 3 次

---

## 4) 首批标准错误码（冻结建议）

### SYS
- `SYS-STATE-001`：PID 存在但端口未监听（假存活）【P0】
- `SYS-UNAVAILABLE-002`：health 不可用【P0】

### ING
- `ING-TIMEOUT-001`：数据源拉取超时【P1】
- `ING-AUTH-002`：上游鉴权失败【P1】
- `ING-DATA-003`：上游数据结构异常【P2】

### MOD
- `MOD-TIMEOUT-001`：模型调用超时【P1】
- `MOD-RATE-002`：模型限流【P1】
- `MOD-UNAVAILABLE-003`：模型服务不可用【P1】
- `MOD-VALIDATION-004`：模型返回格式不合规【P2】

### RTR
- `RTR-STATE-001`：无可用路由通道【P0】
- `RTR-DATA-002`：路由配置非法【P1】

### EXP
- `EXP-DEPENDENCY-001`：导出依赖不可用【P2】
- `EXP-RENDER-002`：导出渲染失败【P2】
- `EXP-DATA-003`：导出内容为空【P3】

### SND
- `SND-NET-001`：发送网关连接失败【P1】
- `SND-VALIDATION-002`：发送参数缺失/非法【P2】
- `SND-STATE-003`：发送回执超时【P2】

### DB
- `DB-UNAVAILABLE-001`：数据库不可写/锁冲突【P0】
- `DB-DATA-002`：数据结构不一致【P1】

### CFG
- `CFG-VALIDATION-001`：配置字段非法【P2】
- `CFG-STATE-002`：关键配置缺失【P1】

---

## 5) 前端展示规范（冻结建议）

1. 所有用户可见错误必须显示 `error_code`
2. 必须包含：
- `human_message`（可理解描述）
- `recover_hint`（下一步建议）
3. 展示方式：
- `P0/P1`：顶部红色横幅
- `P2`：黄色提示条
- `P3`：弱提示或日志区

---

## 6) D2 验收标准（冻结建议）

1. 任一失败日志可映射到标准错误码
2. 前端错误提示包含错误码
3. 可重试错误按统一矩阵执行
4. `P0/P1` 触发时有明确降级动作

---

## 7) 待你确认项

1. `P0/P1` 告警阈值是否按当前建议执行。  
2. `DATA/UNKNOWN` 是否保持“最多1次重试”。  
3. 首批错误码是否直接冻结为 v1。  

