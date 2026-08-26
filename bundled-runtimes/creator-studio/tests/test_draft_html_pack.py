import sys
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from draft_html_pack import normalize_sample_html, write_draft_html_from_markdown


def test_normalize_sample_html_inlines_chartjs_and_editor_contract(tmp_path):
    chartjs_file = tmp_path / "chart.umd.min.js"
    chartjs_file.write_text("window.Chart=function Chart(){return {};};", encoding="utf-8")
    source = tmp_path / "sample.html"
    output = tmp_path / "normalized.html"
    source.write_text(
        """<!DOCTYPE html>
<html><head>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>@import url('https://fonts.example/fonts.css');</style>
</head><body>
<main><canvas id="c"></canvas></main>
<script>
document.addEventListener('DOMContentLoaded',function(){
new Chart(document.getElementById('c'),{type:'log',options:{responsive:true}});
});
</script>
</body></html>
""",
        encoding="utf-8",
    )

    normalize_sample_html(source, output, str(chartjs_file))
    text = output.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/npm/chart.js" not in text
    assert "fonts.example" not in text
    assert "Chart.js v4.4.4 - Inlined by Newma Draft" in text
    assert "window.Chart=function Chart()" in text
    assert '<canvas id="c" width="700" height="350">' in text
    assert "type:'logarithmic'" in text
    assert "responsive:false" in text
    assert 'contenteditable="true"' in text
    assert "免责声明" in text
    assert "dasheng-draft-html-runtime" in text


def test_write_draft_html_from_markdown_keeps_table_labels_inside_span(tmp_path):
    draft = tmp_path / "draft.md"
    output = tmp_path / "draft.html"
    chartjs_file = tmp_path / "chart.umd.min.js"
    chartjs_file.write_text("window.Chart=function Chart(){return {};};", encoding="utf-8")
    draft.write_text(
        """# 测试标题

## 一、判断

这里是一段正文。

| 标签 | 数值 |
| --- | --- |
| 政策 | 城市更新 |
""",
        encoding="utf-8",
    )

    write_draft_html_from_markdown(
        draft,
        output,
        title="测试标题",
        chart_specs=[
            {
                "id": "topic-1-claim-01-chart",
                "title": "成交量与价格走势",
                "type": "bar",
                "labels": ["一月", "二月"],
                "datasets": [{"label": "成交量", "data": [10, 12], "backgroundColor": "#1a6fb5"}],
                "source": "测试来源",
            }
        ],
        image_specs=[
            {
                "title": "测试配图",
                "data_uri": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                "caption": "测试图片",
            }
        ],
        chartjs_file=str(chartjs_file),
    )
    text = output.read_text(encoding="utf-8")

    assert "<td><span>政策</span></td>" in text
    assert '<main class="page" data-dasheng-edit-root="true" contenteditable="true">' in text
    assert "图表计划" not in text
    assert "Draft Research Framework" not in text
    assert '<canvas id="topic-1-claim-01-chart" width="700" height="350">' in text
    assert "dasheng-draft-chart-runtime" in text
    assert "data:image/jpeg;base64," in text
    assert "window.Chart=function Chart()" in text
    assert "免责声明" in text
    assert "cdn.jsdelivr" not in text


def test_write_draft_html_from_markdown_without_specs_does_not_fake_assets(tmp_path):
    draft = tmp_path / "draft.md"
    output = tmp_path / "draft.html"
    draft.write_text("# 测试标题\n\n## 一、判断\n\n这里是一段正文。", encoding="utf-8")

    write_draft_html_from_markdown(
        draft,
        output,
        title="测试标题",
        chart_needs=["topic-1-claim-01｜成交量与价格走势"],
        visual_needs=["研究框架图"],
    )
    text = output.read_text(encoding="utf-8")

    assert "图表计划" not in text
    assert "Draft Research Framework" not in text
    assert re.search(r"<canvas\b", text) is None
    assert "data:image/" not in text
    assert "cdn.jsdelivr" not in text
