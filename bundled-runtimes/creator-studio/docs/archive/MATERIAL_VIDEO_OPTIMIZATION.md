# Material 阶段视频素材优化方案

## 当前问题

### 1. 视频默认不下载
- `--video-download-limit` 默认值为 0
- 需要手动指定才会下载视频
- 不符合自动化工作流需求

### 2. 文件目录结构复杂
当前目录结构：
```
产物/04_Material/{run_id}/
├── topic-ai-ma-boom-q1-2026/
│   ├── charts/
│   │   ├── 01_gdp_growth.csv
│   │   └── 01_gdp_growth.png
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
└── topic-china-15th-five-year-plan-2026/
    └── ...
```

**问题**：
- 多级目录（charts/, images/web_search/, images/generated/, videos/web_search/）
- 编辑人员需要在多个文件夹中查找素材
- 不便于快速定位和使用

### 3. 文件命名不够直观
当前命名：
- `01__tesla_factory_tour.mp4` - 序号 + 标题
- `01_01__elon_musk.jpg` - 序号 + 查询词

**问题**：
- 序号不能直接反映内容
- 查询词可能与实际内容不完全匹配
- 编辑人员需要打开文件才能确认内容

## 优化方案

### 1. 自动下载视频

**修改**: 将 `--video-download-limit` 默认值从 0 改为 3

```python
# material_execute_pack.py line 3235
parser.add_argument("--video-download-limit", type=int, default=3)  # 改为 3
```

**效果**：
- 每个查询自动下载前 3 个合格视频
- 无需手动指定参数
- 符合自动化工作流

### 2. 扁平化文件结构

**目标结构**：
```
产物/04_Material/{run_id}/
├── topic-ai-ma-boom-q1-2026/
│   ├── 图表_GDP增长趋势.png
│   ├── 图表_GDP增长趋势.csv
│   ├── 图表_AI投资规模.png
│   ├── 图表_AI投资规模.csv
│   ├── 图片_Elon_Musk.jpg
│   ├── 图片_Tesla工厂.jpg
│   ├── 图片_封面_AI并购.png
│   ├── 图片_信息图_投资分布.png
│   ├── 视频_Tesla工厂参观.mp4
│   └── 视频_SpaceX发射.mp4
└── topic-china-15th-five-year-plan-2026/
    └── ...
```

**优势**：
- ✅ 单层目录，所有素材在同一文件夹
- ✅ 文件名前缀标识类型（图表、图片、视频）
- ✅ 文件名包含内容描述
- ✅ 便于编辑人员快速查找

### 3. 优化文件命名

**命名规则**：

#### 图表文件
```
图表_{描述性标题}.png
图表_{描述性标题}.csv
```
示例：
- `图表_GDP增长趋势.png`
- `图表_AI投资规模对比.png`
- `图表_市场份额分布.png`

#### 图片文件
```
图片_{实体名称或描述}.jpg
图片_封面_{主题}.png
图片_信息图_{内容}.png
```
示例：
- `图片_Elon_Musk.jpg`
- `图片_Tesla工厂外观.jpg`
- `图片_封面_AI并购狂潮.png`
- `图片_信息图_投资分布.png`

#### 视频文件
```
视频_{内容描述}.mp4
```
示例：
- `视频_Tesla工厂参观.mp4`
- `视频_SpaceX火箭发射.mp4`
- `视频_AI技术演示.mp4`

**命名原则**：
1. 使用中文前缀（图表、图片、视频）便于分类
2. 描述性标题反映实际内容
3. 避免序号，使用有意义的名称
4. 长度控制在 30 字以内
5. 避免特殊字符，使用下划线分隔

## 实施步骤

### Step 1: 修改默认下载限制

**文件**: `${DASHENG_PROJECT_ROOT}/scripts/material_execute_pack.py`

```python
# Line 3235
parser.add_argument("--video-download-limit", type=int, default=3)
```

### Step 2: 修改文件输出路径

**当前代码**（Line 1984）：
```python
outtmpl = str(topic.topic_root / "videos" / "web_search" / f"{idx:02d}__%(title).80B.%(ext)s")
```

**修改为**：
```python
# 生成描述性文件名
video_desc = safe_slug(query)[:30]  # 使用查询词作为描述
outtmpl = str(topic.topic_root / f"视频_{video_desc}.%(ext)s")
```

### Step 3: 修改图表输出路径

**当前代码**（散布在各个 execute_*_charts 函数中）：
```python
csv_path = topic.topic_root / "charts" / f"{chart_id}.csv"
png_path = topic.topic_root / "charts" / f"{chart_id}.png"
```

**修改为**：
```python
csv_path = topic.topic_root / f"图表_{chart_title}.csv"
png_path = topic.topic_root / f"图表_{chart_title}.png"
```

### Step 4: 修改图片输出路径

**当前代码**（Line 1531）：
```python
filename = f"{idx:02d}_{candidate_rank:02d}__{safe_slug(query)[:60]}{suffix}"
out = topic.topic_root / "images" / "web_search" / filename
```

**修改为**：
```python
# 根据实体类型生成描述性文件名
entity_name = record.get("entity", query)
filename = f"图片_{safe_slug(entity_name)[:30]}{suffix}"
out = topic.topic_root / filename
```

### Step 5: 修改 AI 生成图片输出路径

**当前代码**（Line 2125）：
```python
"image": str(topic.topic_root / "images" / "generated" / image_name)
```

**修改为**：
```python
# 根据图片类型生成描述性文件名
if task_id == "cover":
    filename = f"图片_封面_{topic.title[:20]}.png"
elif task_id.startswith("infographic_"):
    filename = f"图片_信息图_{idx}.png"
elif task_id.startswith("frame_"):
    filename = f"图片_漫画_{idx}.png"
# ...
"image": str(topic.topic_root / filename)
```

### Step 6: 更新 manifest 文件路径

所有 manifest 文件保持在原位置，但记录的文件路径需要更新为新的扁平化路径。

## 兼容性考虑

### 向后兼容

为了不破坏现有工作流，建议：

1. **保留旧目录结构作为备份**
   - 在新位置创建文件的同时，保留旧位置的副本
   - 或者在 manifest 中同时记录新旧路径

2. **添加配置开关**
   ```python
   parser.add_argument("--flat-structure", action="store_true", 
                       help="Use flat directory structure for materials")
   ```

3. **渐进式迁移**
   - 先在新 run_id 中使用新结构
   - 旧 run_id 保持原有结构不变

## 测试计划

### 测试用例 1: 视频自动下载

```bash
cd ${DASHENG_PROJECT_ROOT}

# 不指定 --video-download-limit，应该自动下载 3 个视频
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/test_run" \
  --steps video_search

# 验证：检查是否下载了视频
ls 产物/04_Material/test_run/topic-*/视频_*.mp4
```

### 测试用例 2: 扁平化文件结构

```bash
# 执行所有步骤
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/test_run" \
  --steps charts,image_search,video_search,ai_prep \
  --flat-structure

# 验证：所有素材在同一目录
ls 产物/04_Material/test_run/topic-*/

# 应该看到：
# 图表_*.png
# 图表_*.csv
# 图片_*.jpg
# 图片_封面_*.png
# 视频_*.mp4
```

### 测试用例 3: 文件命名

```bash
# 检查文件名是否符合规范
ls 产物/04_Material/test_run/topic-*/ | grep "^图表_"
ls 产物/04_Material/test_run/topic-*/ | grep "^图片_"
ls 产物/04_Material/test_run/topic-*/ | grep "^视频_"

# 验证：
# - 文件名包含中文前缀
# - 文件名描述性强
# - 没有序号前缀
```

## 预期效果

### 编辑人员体验改善

**优化前**：
1. 打开 `产物/04_Material/{run_id}/topic-xxx/`
2. 进入 `charts/` 查看图表
3. 进入 `images/web_search/` 查看搜索图片
4. 进入 `images/generated/` 查看 AI 图片
5. 进入 `videos/web_search/` 查看视频
6. 需要打开文件才能确认内容

**优化后**：
1. 打开 `产物/04_Material/{run_id}/topic-xxx/`
2. 所有素材在同一目录，按类型和名称排序
3. 文件名直接反映内容，无需打开即可确认
4. 快速定位需要的素材

### 工作流改善

**优化前**：
```bash
# 需要手动指定下载视频
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}" \
  --steps charts,image_search,video_search,ai_prep \
  --video-download-limit 3  # 必须指定
```

**优化后**：
```bash
# 自动下载视频
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}" \
  --steps charts,image_search,video_search,ai_prep
  # 无需指定 --video-download-limit
```

## 风险评估

### 低风险
- ✅ 修改默认参数值（向后兼容）
- ✅ 添加新的命名规则（不影响现有逻辑）

### 中风险
- ⚠️ 修改文件输出路径（需要更新所有引用）
- ⚠️ 修改 manifest 文件格式（需要更新读取逻辑）

### 高风险
- ❌ 删除旧目录结构（可能破坏现有工作流）

**建议**：采用渐进式迁移，先添加新功能，再逐步废弃旧功能。

## 实施优先级

### P0（立即实施）
1. 修改 `--video-download-limit` 默认值为 3
2. 文档化新的文件命名规范

### P1（1周内）
1. 实现扁平化文件结构
2. 实现描述性文件命名
3. 更新 manifest 文件格式

### P2（2周内）
1. 添加向后兼容开关
2. 完整测试和验证
3. 更新相关文档

### P3（1个月内）
1. 迁移现有 run_id 到新结构
2. 废弃旧目录结构
3. 清理冗余代码

---

**创建时间**: 2026-04-06  
**状态**: 📋 方案待实施  
**优先级**: P0 + P1  
**预计工时**: 4-6 小时
