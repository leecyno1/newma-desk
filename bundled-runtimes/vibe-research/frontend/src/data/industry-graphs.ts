import type { GraphArtifactInput } from "@/lib/artifacts";

const HUMANOID_SOURCE = `# 人形机器人基础产业链

## 边界
以通用人形机器人整机为中心，覆盖感知、计算控制、执行器、能源与结构、系统集成、验证和应用；不把单一零部件清单误当成完整产业链。

## 主链路
上游核心零部件与软件能力 → 关节/灵巧手/感知控制等功能模组 → 肢体和机身子系统 → 整机集成 → 测试验证 → 工业、物流服务和特种/家庭应用。

## 关键认识
- 旋转关节和直线关节是两条并行执行器路线，不能串成前后工序。
- 具身模型、运动控制和感知控制贯穿整机，不属于单一机械部件的下游。
- 六维力、关节力矩和触觉器件既服务全身控制，也直接决定灵巧手闭环能力。
- 量产瓶颈集中在高功率密度执行器、寿命一致性、轻量化、能耗、安全和真实场景数据闭环。
`;

const OPTICAL_MODULE_SOURCE = `# 光模块与高速光互联基础产业链

## 边界
以数据中心和通信网络使用的高速光收发产品为中心，覆盖光电芯片、模拟/数字芯片、无源光学、光引擎、封装测试，以及可插拔、LPO、CPO 三条产品路线。

## 主链路
上游光电芯片/IC/无源器件/封装材料 → 发射与接收光引擎 → 封装测试 → 可插拔光模块、LPO 或 CPO → 交换机/路由器/网卡 → AI 集群网络与电信网络。

## 关键认识
- 光模块不是“光芯片 → CPO”的单线结构；可插拔、LPO、CPO 是并行演进路线。
- DSP/CDR 是传统高速可插拔模块的重要环节，LPO 的核心变化是减少模块内 DSP，转而依赖系统级 SerDes 与链路工程。
- CPO 把光引擎靠近或共封装于交换 ASIC，仍依赖激光、硅光/光芯片、耦合、封装和光纤连接。
- 需求由端口速率、交换容量、距离、功耗、散热、误码率和可靠性共同约束。
`;

export const BASE_INDUSTRY_GRAPHS: Record<string, GraphArtifactInput> = {
  humanoid: {
    moduleId: "industry-map",
    title: "人形机器人基础产业链图谱",
    subtitle: "基础图谱 v1 · 零部件、功能模组、整机与应用的多分支关系",
    nodes: [
      { id: "requirements", label: "场景需求与性能指标", subtitle: "负载 · 速度 · 精度 · 续航 · 成本 · 安全", kind: "source", group: "需求定义" },
      { id: "data-sim", label: "数据采集与仿真训练", subtitle: "遥操作 · 动作数据 · 数字孪生 · 强化学习", kind: "source", group: "数据与训练" },
      { id: "embodied-model", label: "具身模型与任务规划", subtitle: "视觉语言动作模型 · 世界模型 · 任务分解", kind: "component", group: "软件智能" },
      { id: "vision-sensing", label: "视觉与状态感知", subtitle: "相机 · 深度传感器 · IMU · 编码器 · 麦克风", kind: "component", group: "感知零部件" },
      { id: "force-tactile", label: "力觉与触觉", subtitle: "六维力 · 关节扭矩 · 指尖触觉 · 电子皮肤", kind: "component", group: "感知零部件" },
      { id: "compute-control", label: "计算与伺服控制", subtitle: "AI SoC · MCU · 实时控制器 · 伺服驱动器", kind: "component", group: "电子电控" },
      { id: "mechatronic-integration", label: "机电模组与肢体集成", subtitle: "关节布局 · 肢体装配 · 线束 · 热管理 · 标定", kind: "infrastructure", group: "子系统集成" },
      { id: "rotary-parts", label: "旋转执行器零部件", subtitle: "无框力矩电机 · 谐波/行星减速器 · 轴承 · 编码器 · 制动器", kind: "material", group: "核心零部件" },
      { id: "linear-parts", label: "直线执行器零部件", subtitle: "行星滚柱/滚珠丝杠 · 电机 · 导轨 · 轴承", kind: "material", group: "核心零部件" },
      { id: "hand-parts", label: "灵巧手零部件", subtitle: "微型电机 · 微型减速器 · 腱绳 · 触觉阵列", kind: "material", group: "核心零部件" },
      { id: "power-body-parts", label: "能源、结构与连接", subtitle: "电芯/BMS · 功率器件 · 轻量化结构件 · 线束 · 连接器", kind: "material", group: "核心零部件" },
      { id: "rotary-joint", label: "旋转关节模组", subtitle: "肩/肘/腕/髋等高扭矩密度一体化关节", kind: "component", group: "功能模组" },
      { id: "linear-joint", label: "直线关节模组", subtitle: "膝/踝等高推力、高刚度直线执行单元", kind: "component", group: "功能模组" },
      { id: "dexterous-hand", label: "灵巧手总成", subtitle: "多自由度手指 · 抓取机构 · 触觉闭环", kind: "component", group: "功能模组" },
      { id: "perception-control", label: "感知与控制系统", subtitle: "环境理解 · 状态估计 · 实时闭环 · 通信总线", kind: "component", group: "功能模组" },
      { id: "body-energy", label: "机身、骨架与能源系统", subtitle: "躯干 · 轻量化骨架 · 电池包 · 配电与热管理", kind: "component", group: "功能模组" },
      { id: "sensor-fusion", label: "传感融合与状态估计", subtitle: "视觉/惯导融合 · 接触状态 · 关节与机身状态估计", kind: "component", group: "感知控制" },
      { id: "subsystem-integration", label: "肢体与机身子系统集成", subtitle: "手臂 · 腿足 · 躯干 · 头部 · 线束与热管理集成", kind: "infrastructure", group: "系统集成" },
      { id: "robot-oem", label: "整机设计与制造", subtitle: "机械/电子/软件协同 · 供应链管理 · 量产装配", kind: "infrastructure", group: "整机" },
      { id: "verification", label: "测试验证与安全认证", subtitle: "寿命 · 跌倒 · EMC · 功能安全 · 场景可靠性", kind: "infrastructure", group: "验证交付" },
      { id: "industrial-app", label: "工业制造", subtitle: "搬运 · 上下料 · 装配 · 巡检 · 柔性生产", kind: "market", group: "下游应用" },
      { id: "service-app", label: "物流与商业服务", subtitle: "仓储 · 配送 · 零售 · 清洁 · 公共服务", kind: "market", group: "下游应用" },
      { id: "special-home-app", label: "特种与家庭场景", subtitle: "危险作业 · 救援 · 康养 · 家庭助理", kind: "market", group: "下游应用" },
    ],
    edges: [
      { source: "requirements", target: "embodied-model", label: "任务与能力定义", kind: "dependency" },
      { source: "data-sim", target: "embodied-model", label: "训练数据", kind: "supply" },
      { source: "embodied-model", target: "perception-control", label: "任务、步态与运动策略", kind: "flow" },
      { source: "vision-sensing", target: "sensor-fusion", label: "环境与姿态信号", kind: "supply" },
      { source: "force-tactile", target: "sensor-fusion", label: "力控反馈", kind: "supply" },
      { source: "compute-control", target: "sensor-fusion", label: "实时计算", kind: "supply" },
      { source: "sensor-fusion", target: "perception-control", label: "融合状态与反馈", kind: "flow" },
      { source: "compute-control", target: "rotary-joint", label: "伺服驱动", kind: "supply" },
      { source: "compute-control", target: "linear-joint", label: "伺服驱动", kind: "supply" },
      { source: "rotary-parts", target: "rotary-joint", label: "机电传动集成", kind: "supply" },
      { source: "linear-parts", target: "linear-joint", label: "机电传动集成", kind: "supply" },
      { source: "hand-parts", target: "dexterous-hand", label: "微型执行与传动", kind: "supply" },
      { source: "force-tactile", target: "dexterous-hand", label: "触觉闭环", kind: "supply" },
      { source: "power-body-parts", target: "body-energy", label: "结构与能源供给", kind: "supply" },
      { source: "rotary-joint", target: "mechatronic-integration", label: "上肢/髋部执行", kind: "flow" },
      { source: "linear-joint", target: "mechatronic-integration", label: "腿足执行", kind: "flow" },
      { source: "dexterous-hand", target: "mechatronic-integration", label: "末端操作", kind: "flow" },
      { source: "body-energy", target: "mechatronic-integration", label: "承载与供能", kind: "flow" },
      { source: "mechatronic-integration", target: "subsystem-integration", label: "机电肢体子系统", kind: "flow" },
      { source: "perception-control", target: "subsystem-integration", label: "感知控制闭环", kind: "flow" },
      { source: "subsystem-integration", target: "robot-oem", label: "整机装配集成", kind: "flow" },
      { source: "robot-oem", target: "verification", label: "工程样机与量产验证", kind: "flow" },
      { source: "verification", target: "industrial-app", label: "工业交付", kind: "flow" },
      { source: "verification", target: "service-app", label: "商业化部署", kind: "flow" },
      { source: "verification", target: "special-home-app", label: "安全准入与部署", kind: "flow" },
    ],
    sourceText: HUMANOID_SOURCE,
    sources: [
      "International Federation of Robotics（机器人产业边界与应用分类）",
      "NVIDIA Isaac / GR00T（仿真、训练与具身智能技术栈）",
      "Harmonic Drive、Kollmorgen 等厂商公开产品资料（关节传动与无框电机）",
      "公开整机技术资料与通用机电系统工程拆解；整理日期 2026-07-23",
    ],
    metadata: {
      sectorKey: "humanoid",
      artifactRole: "base",
      baseVersion: "2026-07-23.1",
      graphModel: "multi-branch-value-chain",
    },
  },

  cpo: {
    moduleId: "industry-map",
    title: "光模块与高速光互联基础产业链图谱",
    subtitle: "基础图谱 v1 · 可插拔、LPO、CPO 三条并行路线",
    nodes: [
      { id: "bandwidth-demand", label: "带宽、距离与功耗需求", subtitle: "AI 集群扩容 · 端口速率升级 · 网络架构演进", kind: "source", group: "需求定义" },
      { id: "standards", label: "接口与互操作标准", subtitle: "IEEE 802.3 · OIF/CMIS · MSA · 以太网/InfiniBand", kind: "external", group: "标准生态" },
      { id: "product-definition", label: "产品定义与链路工程", subtitle: "速率 · 距离 · 波长 · 功耗 · 误码率 · 可靠性预算", kind: "component", group: "产品规划" },
      { id: "laser-chip", label: "激光器芯片与光源", subtitle: "VCSEL · DFB · EML · CW Laser · InP/GaAs 外延", kind: "material", group: "上游光芯片" },
      { id: "detector-chip", label: "探测器芯片", subtitle: "PIN · APD · 光电探测阵列", kind: "material", group: "上游光芯片" },
      { id: "silicon-photonics", label: "硅光与光子集成芯片", subtitle: "调制器 · 波导 · 耦合器 · WDM · PIC", kind: "material", group: "上游光芯片" },
      { id: "analog-ic", label: "模拟前端芯片", subtitle: "Laser Driver · TIA · 线性驱动/放大", kind: "component", group: "上游电芯片" },
      { id: "dsp-cdr", label: "DSP、CDR 与控制芯片", subtitle: "均衡 · FEC · 时钟恢复 · MCU · 电源管理", kind: "component", group: "上游电芯片" },
      { id: "passive-optics", label: "无源光学器件", subtitle: "透镜 · 隔离器 · 滤光片 · AWG · FAU · 光环行器", kind: "material", group: "上游器件" },
      { id: "fiber-connector", label: "光纤、连接器与线缆", subtitle: "光纤/带纤 · MPO/LC · MT 插芯 · 尾纤", kind: "material", group: "上游器件" },
      { id: "package-material", label: "封装、PCB 与热管理材料", subtitle: "陶瓷/金属壳体 · 高速 PCB · 基板 · 胶材 · 散热件", kind: "material", group: "上游器件" },
      { id: "tx-engine", label: "发射光引擎", subtitle: "光源/调制 · 驱动 · 耦合 · 波分复用", kind: "component", group: "光引擎" },
      { id: "rx-engine", label: "接收光引擎", subtitle: "解复用 · 探测 · TIA · 信号恢复", kind: "component", group: "光引擎" },
      { id: "silicon-engine", label: "硅光集成光引擎", subtitle: "PIC + 外置/集成光源 + 光纤耦合", kind: "component", group: "光引擎" },
      { id: "electrical-engine", label: "高速电接口与控制子系统", subtitle: "DSP/CDR 或线性链路 · 驱动/TIA · MCU · 电源管理", kind: "component", group: "电接口" },
      { id: "optical-assembly", label: "光纤连接与封装子组件", subtitle: "FAU/尾纤 · MPO/LC · 壳体/基板 · PCB · 散热", kind: "component", group: "封装子组件" },
      { id: "package-test", label: "精密封装与测试", subtitle: "光电耦合 · 芯片贴装 · 校准 · 老化 · 误码与可靠性测试", kind: "infrastructure", group: "中游制造" },
      { id: "pluggable", label: "高速可插拔光模块", subtitle: "400G/800G/1.6T · DR/FR/LR/ZR · 模块内 DSP", kind: "infrastructure", group: "产品路线" },
      { id: "lpo", label: "LPO 线性光模块", subtitle: "减少模块内 DSP · 依赖系统 SerDes 与链路工程", kind: "infrastructure", group: "产品路线" },
      { id: "cpo-route", label: "CPO 光引擎/共封装", subtitle: "光引擎靠近或共封装于交换 ASIC · 外置激光可选", kind: "infrastructure", group: "产品路线" },
      { id: "system-integration", label: "交换芯片与光接口系统集成", subtitle: "交换 ASIC/SerDes · NIC/DPU · 前面板或共封装光 I/O", kind: "component", group: "系统集成" },
      { id: "network-equipment", label: "交换机、路由器与传输设备", subtitle: "盒式交换机 · 光电共封装设备 · OTN/接入设备", kind: "infrastructure", group: "系统设备" },
      { id: "ai-fabric", label: "AI 集群高速网络", subtitle: "Scale-up / Scale-out · 叶脊网络 · GPU/加速器互联", kind: "market", group: "下游网络" },
      { id: "telecom-network", label: "电信传输与接入网络", subtitle: "城域/骨干 · 5G 承载 · PON · 数据中心互联", kind: "market", group: "下游网络" },
      { id: "operators", label: "云厂商、IDC 与运营商", subtitle: "资本开支 · 网络建设 · 运维与替换需求", kind: "market", group: "终端客户" },
    ],
    edges: [
      { source: "bandwidth-demand", target: "product-definition", label: "容量、距离与功耗目标", kind: "dependency" },
      { source: "standards", target: "product-definition", label: "接口与管理约束", kind: "dependency" },
      { source: "laser-chip", target: "tx-engine", label: "光源/调制发射", kind: "supply" },
      { source: "analog-ic", target: "tx-engine", label: "高速驱动", kind: "supply" },
      { source: "detector-chip", target: "rx-engine", label: "光电转换", kind: "supply" },
      { source: "analog-ic", target: "rx-engine", label: "跨阻放大", kind: "supply" },
      { source: "passive-optics", target: "tx-engine", label: "复用、准直与耦合", kind: "supply" },
      { source: "passive-optics", target: "rx-engine", label: "解复用与耦合", kind: "supply" },
      { source: "silicon-photonics", target: "silicon-engine", label: "光子集成平台", kind: "supply" },
      { source: "laser-chip", target: "silicon-engine", label: "集成/外置光源", kind: "supply" },
      { source: "dsp-cdr", target: "electrical-engine", label: "均衡/FEC/CDR", kind: "supply" },
      { source: "analog-ic", target: "electrical-engine", label: "高速驱动与接收", kind: "supply" },
      { source: "fiber-connector", target: "optical-assembly", label: "光纤耦合与连接", kind: "supply" },
      { source: "package-material", target: "optical-assembly", label: "封装、PCB 与散热", kind: "supply" },
      { source: "tx-engine", target: "package-test", label: "发射组件", kind: "flow" },
      { source: "rx-engine", target: "package-test", label: "接收组件", kind: "flow" },
      { source: "silicon-engine", target: "package-test", label: "集成光引擎", kind: "flow" },
      { source: "electrical-engine", target: "package-test", label: "电接口与控制", kind: "flow" },
      { source: "optical-assembly", target: "package-test", label: "光纤与结构封装", kind: "flow" },
      { source: "product-definition", target: "package-test", label: "设计、工艺与测试规范", kind: "dependency" },
      { source: "package-test", target: "pluggable", label: "模块封装与验证", kind: "flow" },
      { source: "package-test", target: "lpo", label: "线性光学封装", kind: "flow" },
      { source: "package-test", target: "cpo-route", label: "高密度光引擎封装", kind: "flow" },
      { source: "pluggable", target: "system-integration", label: "可插拔光接口", kind: "flow" },
      { source: "lpo", target: "system-integration", label: "线性光接口", kind: "flow" },
      { source: "cpo-route", target: "system-integration", label: "共封装光 I/O", kind: "flow" },
      { source: "system-integration", target: "network-equipment", label: "交换、网络卸载与光接口", kind: "flow" },
      { source: "network-equipment", target: "ai-fabric", label: "集群互联设备", kind: "flow" },
      { source: "network-equipment", target: "telecom-network", label: "传输与接入设备", kind: "flow" },
      { source: "ai-fabric", target: "operators", label: "云与 IDC 部署", kind: "flow" },
      { source: "telecom-network", target: "operators", label: "运营商网络部署", kind: "flow" },
    ],
    sourceText: OPTICAL_MODULE_SOURCE,
    sources: [
      "IEEE 802.3 Ethernet 工作组（端口速率与物理层标准）",
      "OIF / CMIS / 行业 MSA（高速接口、管理和共封装互操作）",
      "公开光器件、DSP、交换芯片与模块厂商产品资料",
      "数据中心光互联通用工程架构；整理日期 2026-07-23",
    ],
    metadata: {
      sectorKey: "cpo",
      artifactRole: "base",
      baseVersion: "2026-07-23.1",
      graphModel: "multi-route-value-chain",
    },
  },
};

export function getBaseIndustryGraph(sectorKey: string): GraphArtifactInput | null {
  return BASE_INDUSTRY_GRAPHS[sectorKey] ?? null;
}
