import heapq
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vibe_visualization_api.artifacts.models import GraphArtifactCreate, GraphNode


class ArtifactRenderError(Exception):
    """Raised when Archify cannot render a validated graph artifact."""


NEWMA_THEME_ADAPTER = r"""
  <style data-newma-archify-theme-adapter>
    html[data-newma-theme] {
      --bg: var(--vibe-bg);
      --grid: var(--vibe-border);
      --text: var(--vibe-text);
      --text-muted: var(--vibe-text-muted);
      --text-dim: var(--vibe-text-faint);
      --text-faint: var(--vibe-text-faint);
      --panel: color-mix(in srgb, var(--vibe-surface) 94%, transparent);
      --panel-border: var(--vibe-border);
      --lane-fill: color-mix(in srgb, var(--vibe-surface-muted) 72%, transparent);
      --lane-stroke: var(--vibe-border-strong);
      --arrow: var(--vibe-text-faint);
      --arrow-emphasis: var(--vibe-accent);
      --mask: var(--vibe-surface);
      --frontend-fill: color-mix(in srgb, var(--vibe-chart-series-1) 14%, transparent);
      --frontend-stroke: var(--vibe-chart-series-1);
      --backend-fill: color-mix(in srgb, var(--vibe-chart-series-2) 14%, transparent);
      --backend-stroke: var(--vibe-chart-series-2);
      --database-fill: color-mix(in srgb, var(--vibe-chart-series-3) 14%, transparent);
      --database-stroke: var(--vibe-chart-series-3);
      --cloud-fill: color-mix(in srgb, var(--vibe-chart-series-4) 14%, transparent);
      --cloud-stroke: var(--vibe-chart-series-4);
      --security-fill: color-mix(in srgb, var(--vibe-error) 13%, transparent);
      --security-stroke: var(--vibe-error);
      --messagebus-fill: color-mix(in srgb, var(--vibe-chart-series-5) 14%, transparent);
      --messagebus-stroke: var(--vibe-chart-series-5);
      --external-fill: color-mix(in srgb, var(--vibe-text-muted) 12%, transparent);
      --external-stroke: var(--vibe-text-muted);
      --toolbar-bg: color-mix(in srgb, var(--vibe-surface-raised) 92%, transparent);
      --toolbar-border: var(--vibe-border-strong);
      --toolbar-text: var(--vibe-text);
      --toolbar-hover: var(--vibe-surface-selected);
      --toolbar-menu-bg: var(--vibe-surface-raised);
      background: var(--vibe-bg);
      color: var(--vibe-text);
    }
    html[data-newma-theme] body { background: var(--vibe-bg); color: var(--vibe-text); }
  </style>
  <script data-newma-archify-theme-adapter>
    (function () {
      var palettes = {
        light: {
          '--vibe-bg':'#f4efe3','--vibe-surface':'#fbf7ef','--vibe-surface-muted':'#eae1d0',
          '--vibe-surface-raised':'#fffaf1','--vibe-surface-selected':'#e0d2b5',
          '--vibe-border':'#d8cdbb','--vibe-border-strong':'#b9aa90','--vibe-text':'#173128',
          '--vibe-text-muted':'#66766e','--vibe-text-faint':'#89958d','--vibe-accent':'#a87432',
          '--vibe-error':'#b91c1c','--vibe-chart-series-1':'#a87432','--vibe-chart-series-2':'#3f7667',
          '--vibe-chart-series-3':'#8f6b50','--vibe-chart-series-4':'#77825c','--vibe-chart-series-5':'#a45e52'
        },
        dark: {
          '--vibe-bg':'#0f1714','--vibe-surface':'#16211c','--vibe-surface-muted':'#121d18',
          '--vibe-surface-raised':'#1a2821','--vibe-surface-selected':'#2a382e',
          '--vibe-border':'#2a3931','--vibe-border-strong':'#405146','--vibe-text':'#f3ecdd',
          '--vibe-text-muted':'#a8b4a5','--vibe-text-faint':'#78847a','--vibe-accent':'#c89a5a',
          '--vibe-error':'#f87171','--vibe-chart-series-1':'#c89a5a','--vibe-chart-series-2':'#70a596',
          '--vibe-chart-series-3':'#b67b64','--vibe-chart-series-4':'#9da96f','--vibe-chart-series-5':'#cf756b'
        }
      };
      var applied = [];
      var appliedMode = null;
      var hostMode = null;
      var hostVars = null;
      function applyTheme(mode, incoming) {
        mode = mode === 'dark' ? 'dark' : 'light';
        var root = document.documentElement;
        var values = Object.assign({}, palettes[mode]);
        if (incoming && typeof incoming === 'object') {
          Object.keys(values).forEach(function (name) {
            var value = incoming[name];
            if (typeof value === 'string' && value.length <= 200) values[name] = value;
          });
        }
        applied.forEach(function (name) { root.style.removeProperty(name); });
        applied = Object.keys(values);
        applied.forEach(function (name) { root.style.setProperty(name, values[name]); });
        root.dataset.theme = mode;
        root.dataset.newmaTheme = 'true';
        root.style.colorScheme = mode;
        appliedMode = mode;
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute('content', values['--vibe-bg']);
        window.dispatchEvent(new CustomEvent('newma:themechange', { detail: { mode: mode } }));
      }
      window.addEventListener('message', function (event) {
        if (event.source !== window.parent) return;
        var data = event.data;
        if (!data || data.type !== 'newma:artifact-theme') return;
        hostMode = data.mode === 'dark' ? 'dark' : 'light';
        hostVars = data.cssVars;
        applyTheme(hostMode, hostVars);
      });
      var initial = document.documentElement.dataset.theme;
      applyTheme(initial === 'dark' ? 'dark' : 'light');
      new MutationObserver(function () {
        var requested = hostMode || (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
        if (requested !== appliedMode || document.documentElement.dataset.theme !== requested) {
          applyTheme(requested, hostMode ? hostVars : null);
        }
      }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    })();
  </script>
"""


def inject_newma_theme_adapter(html: str) -> str:
    """Make generated and historical Archify views inherit Newma safely."""
    if "data-newma-archify-theme-adapter" in html:
        return html
    marker = "</head>"
    index = html.lower().find(marker)
    if index < 0:
        raise ArtifactRenderError("Archify produced HTML without a head element")
    return f"{html[:index]}{NEWMA_THEME_ADAPTER}{html[index:]}"


COMPONENT_TYPES = {
    "source": "external",
    "material": "database",
    "component": "backend",
    "infrastructure": "cloud",
    "market": "frontend",
    "company": "external",
    "risk": "security",
    "external": "external",
}

EDGE_VARIANTS = {
    "flow": "emphasis",
    "dependency": "default",
    "supply": "dashed",
    "risk": "security",
}


def _fallback_component_position(index: int, count: int) -> tuple[int, int]:
    if count <= 5:
        return 60 + index * 330, 150
    columns = 4
    row, column = divmod(index, columns)
    if row % 2 == 1:
        column = columns - 1 - column
    return 60 + column * 290, 110 + row * 190


def _component_positions(spec: GraphArtifactCreate) -> dict[str, tuple[int, int]]:
    """Lay out a DAG by dependency depth while preserving declared node order."""
    node_ids = [node.id for node in spec.nodes]
    order = {node_id: index for index, node_id in enumerate(node_ids)}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in spec.edges:
        outgoing[edge.source].append(edge.target)
        indegree[edge.target] += 1

    ready = [order[node_id] for node_id in node_ids if indegree[node_id] == 0]
    heapq.heapify(ready)
    layer = {node_id: 0 for node_id in node_ids}
    visited: list[str] = []
    while ready:
        node_id = node_ids[heapq.heappop(ready)]
        visited.append(node_id)
        for target in outgoing[node_id]:
            layer[target] = max(layer[target], layer[node_id] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, order[target])

    if len(visited) != len(node_ids):
        return {
            node_id: _fallback_component_position(index, len(node_ids))
            for index, node_id in enumerate(node_ids)
        }

    columns: dict[int, list[str]] = {}
    for node_id in node_ids:
        columns.setdefault(layer[node_id], []).append(node_id)
    max_rows = max(len(items) for items in columns.values())
    positions: dict[str, tuple[int, int]] = {}
    for depth, items in columns.items():
        top = 80 + ((max_rows - len(items)) * 132) // 2
        for row, node_id in enumerate(items):
            positions[node_id] = (60 + depth * 310, top + row * 132)
    return positions


def _component(node: GraphNode, position: tuple[int, int]) -> dict[str, Any]:
    x, y = position
    subtitle = node.subtitle.strip()
    if len(subtitle) > 150:
        subtitle = f"{subtitle[:147]}…"
    return {
        "id": node.id,
        "type": COMPONENT_TYPES[node.kind],
        "label": node.label,
        "sublabel": subtitle,
        "tag": node.group or node.kind,
        "pos": [x, y],
        "size": [190, 86],
    }


def to_archify_ir(spec: GraphArtifactCreate) -> dict[str, Any]:
    node_ids = [node.id for node in spec.nodes]
    positions = _component_positions(spec)
    sources = [item.strip() for item in spec.sources if item.strip()]
    cards: list[dict[str, Any]] = []
    if sources:
        cards.append({"dot": "cyan", "title": "信息来源", "items": sources[:8]})
    cards.append(
        {
            "dot": "emerald",
            "title": "图谱说明",
            "items": [
                f"{len(spec.nodes)} 个节点 · {len(spec.edges)} 条关系",
                "由 Newma-Desk Artifact Adapter 转换并使用 Archify 渲染",
            ],
        }
    )
    return {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": {
            "title": spec.title,
            "subtitle": spec.subtitle,
            "animation": "trace",
            "visual_preset": "signal-flow",
            "quality_profile": "standard",
            "views": [
                {
                    "id": "industry-path",
                    "label": "产业链主路径",
                    "focus": node_ids[: min(len(node_ids), 16)],
                    "note": "沿 Agent 识别并由用户固化的产业链关系逐站查看。",
                }
            ],
        },
        "components": [
            _component(node, positions[node.id])
            for node in spec.nodes
        ],
        "connections": [
            {
                "id": f"edge-{index + 1}",
                "from": edge.source,
                "to": edge.target,
                "label": edge.label,
                "variant": EDGE_VARIANTS[edge.kind],
                "route": "auto",
            }
            for index, edge in enumerate(spec.edges)
        ],
        "cards": cards,
    }


class ArchifyRenderer:
    def __init__(self, archify_root: Path, node_binary: str = "node"):
        self._root = archify_root.resolve()
        self._renderer = (
            self._root / "renderers" / "architecture" / "render-architecture.mjs"
        )
        self._node_binary = node_binary

    def render(self, ir: dict[str, Any]) -> str:
        if not self._renderer.is_file():
            raise ArtifactRenderError("Archify renderer is not installed")
        with tempfile.TemporaryDirectory(prefix="newma-desk-archify-") as directory:
            root = Path(directory)
            source_path = root / "artifact.architecture.json"
            output_path = root / "artifact.html"
            source_path.write_text(
                json.dumps(ir, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                result = subprocess.run(
                    [
                        self._node_binary,
                        str(self._renderer),
                        str(source_path),
                        str(output_path),
                    ],
                    cwd=self._root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ArtifactRenderError("Archify renderer could not start") from error
            if result.returncode != 0:
                diagnostic = (result.stderr or result.stdout).strip()
                raise ArtifactRenderError(
                    f"Archify rejected the graph: {diagnostic[:1200]}"
                )
            try:
                html = output_path.read_text(encoding="utf-8")
            except OSError as error:
                raise ArtifactRenderError("Archify did not produce an HTML view") from error
            if "<!doctype html" not in html.lower() or len(html) > 5_000_000:
                raise ArtifactRenderError("Archify produced an invalid HTML view")
            return inject_newma_theme_adapter(html)
