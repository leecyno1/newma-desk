# Material 阶段扁平化文件结构实施报告

## 实施日期
2026-04-06

## 实施内容

### 1. 视频自动下载优化（P0 - 已完成）

**修改文件**: `${DASHENG_PROJECT_ROOT}/scripts/material_execute_pack.py`

**修改内容**:
- Line 3235: `--video-download-limit` 默认值从 0 改为 3
- 每个查询自动下载前 3 个合格视频

**备份文件**: 
- `${DASHENG_PROJECT_ROOT}/scripts/material_execute_pack.py.backup.{timestamp}`

### 2. 扁平化文件结构（P1 - 已完成）

**修改文件**: `${DASHENG_PROJECT_ROOT}/scripts/material_execute_pack.py`

**修改内容**:

#### 图表文件
- **目录**: `charts/csv/`, `charts/png/` → 根目录
- **命名**: `chart-01_cpi_core.csv` → `图表_美国CPI对比.csv`
- **示例**:
  - `图表_美国CPI对比.csv` / `图表_美国CPI对比.png`
  - `图表_石油黄金通胀预期.csv` / `图表_石油黄金通胀预期.png`
  - `图表_标普500与美债收益率.csv` / `图表_标普500与美债收益率.png`
  - `图表_情景矩阵热力图.csv` / `图表_情景矩阵热力图.png`

#### 图片文件
- **目录**: `images/web_search/` → 根目录
- **命名**: `01_01__elon_musk.jpg` → `图片_Elon_Musk.jpg`
- **逻辑**: 使用实体名称而非序号，长度限制 30 字符

#### 视频文件
- **目录**: `videos/web_search/` → 根目录
- **命名**: `01__tesla_factory_tour.mp4` → `视频_Tesla工厂参观.mp4`
- **逻辑**: 使用查询词描述，长度限制 30 字符

### 3. 文件结构对比

**优化前**:
```
产物/04_Material/{run_id}/
├── topic-ai-ma-boom-q1-2026/
│   ├── charts/
│   │   ├── csv/
│   │   │   ├── chart-01_cpi_core.csv
│   │   │   └── chart-02_oil_gold_breakeven.csv
│   │   └── png/
│   │       ├── chart-01_cpi_core.png
│   │       └── chart-02_oil_gold_breakeven.png
│   ├── images/
│   │   ├── web_search/
│   │   │   ├── 01_01__elon_musk.jpg
│   │   │   └── 02_01__tesla_factory.jpg
│   │   └── generated/
│   │       ├── cover.png
│   │       └── infographic_1.png
│   └── videos/
│       └── web_search/
│           ├── 01__tesla_factory_tour.mp4
│           └── 02__spacex_launch.mp4
```

**优化后**:
```
产物/04_Material/{run_id}/
├── topic-ai-ma-boom-q1-2026/
│   ├── 图表_美国CPI对比.csv
│   ├── 图表_美国CPI对比.png
│   ├── 图表_石油黄金通胀预期.csv
│   ├── 图表_石油黄金通胀预期.png
│   ├── 图片_Elon_Musk.jpg
│   ├── 图片_Tesla工厂.jpg
│   ├── 视频_Tesla工厂参观.mp4
│   └── 视频_SpaceX发射.mp4
```

## 实施方法

### 自动化补丁脚本

创建了两个补丁脚本：

1. **视频下载优化**: `${PROJECTS_ROOT}/newma-media-studio/scripts/patch_material_video_optimization.sh`
   - Bash 脚本
   - 修改默认参数值

2. **扁平化结构**: `${PROJECTS_ROOT}/newma-media-studio/scripts/apply_flat_structure.py`
   - Python 脚本
   - 使用正则表达式批量替换
   - 包含验证和回滚机制

### 执行记录

```bash
# Step 1: 视频下载优化
bash scripts/patch_material_video_optimization.sh
# ✅ 成功: 视频下载默认值已改为 3

# Step 2: 扁平化结构
python3 scripts/apply_flat_structure.py
# ✅ 补丁应用成功
# 备份: material_execute_pack.py.backup.1775446489

# Step 3: 修复 video_desc 变量定义
# 手动修复: 在 line 1986 添加 video_desc 变量定义
```

## 验证计划

### 测试命令

```bash
cd ${DASHENG_PROJECT_ROOT}

# 测试图表生成
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/test_flat" \
  --steps charts

# 测试图片搜索
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/test_flat" \
  --steps image_search

# 测试视频搜索（自动下载 3 个）
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/test_flat" \
  --steps video_search

# 完整测试
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/test_flat" \
  --steps charts,image_search,video_search,ai_prep
```

### 验证检查点

- [ ] 图表文件直接生成在 topic 根目录
- [ ] 图表文件名包含中文前缀 `图表_`
- [ ] 图片文件直接保存在 topic 根目录
- [ ] 图片文件名包含中文前缀 `图片_` 和实体名称
- [ ] 视频文件直接下载到 topic 根目录
- [ ] 视频文件名包含中文前缀 `视频_` 和查询词描述
- [ ] 视频自动下载 3 个（无需手动指定参数）
- [ ] 所有素材在同一目录，便于编辑人员查找

## 优势总结

### 编辑人员体验改善

**优化前**:
1. 打开 `产物/04_Material/{run_id}/topic-xxx/`
2. 进入 `charts/csv/` 或 `charts/png/` 查看图表
3. 进入 `images/web_search/` 查看搜索图片
4. 进入 `images/generated/` 查看 AI 图片
5. 进入 `videos/web_search/` 查看视频
6. 需要打开文件才能确认内容（序号命名不直观）

**优化后**:
1. 打开 `产物/04_Material/{run_id}/topic-xxx/`
2. 所有素材在同一目录，按类型和名称排序
3. 文件名直接反映内容，无需打开即可确认
4. 快速定位需要的素材

### 工作流改善

**优化前**:
```bash
# 需要手动指定下载视频
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}" \
  --steps charts,image_search,video_search,ai_prep \
  --video-download-limit 3  # 必须指定
```

**优化后**:
```bash
# 自动下载视频
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}" \
  --steps charts,image_search,video_search,ai_prep
  # 无需指定 --video-download-limit
```

## 回滚方案

如需回滚到优化前版本：

```bash
# 恢复备份文件
cp ${DASHENG_PROJECT_ROOT}/scripts/material_execute_pack.py.backup.1775446489 \
   ${DASHENG_PROJECT_ROOT}/scripts/material_execute_pack.py
```

## 后续工作

### P2 优先级（2周内）

- [ ] 更新 manifest 文件格式，记录新的文件路径
- [ ] 更新所有读取 material 文件的下游代码
- [ ] 完整端到端测试
- [ ] 更新相关文档

### P3 优先级（1个月内）

- [ ] 实现 AI 生成图片路径优化（当前脚本中已标记但未实现）
- [ ] 迁移现有 run_id 到新结构（可选）
- [ ] 清理冗余代码

## 相关文档

- 优化方案: [MATERIAL_VIDEO_OPTIMIZATION.md](MATERIAL_VIDEO_OPTIMIZATION.md)
- 素材生成总结: [MATERIAL_GENERATION_SUMMARY.md](MATERIAL_GENERATION_SUMMARY.md)
- 补丁脚本: 
  - `scripts/patch_material_video_optimization.sh`
  - `scripts/apply_flat_structure.py`

---

**状态**: ✅ P0 + P1 已完成  
**测试状态**: 待验证  
**下一步**: 执行验证测试
