#!/usr/bin/env python3
"""
Finance Motion 到 Remotion 配置转换器

将 Finance Motion 8787 的 scenes.json 转换为 Remotion 可用的配置文件。
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any


# 模板映射配置
TEMPLATE_MAPPING = {
    "claude-purple": {
        "component": "ClaudePurple",
        "financeMotionStyle": "neon",
        "palette": {
            "primary": "#a855f7",
            "secondary": "#ec4899",
            "background": "#1a0b2e",
            "text": "#ffffff"
        }
    },
    "cyberpunk": {
        "component": "Cyberpunk",
        "financeMotionStyle": "neon",
        "palette": {
            "primary": "#00ffff",
            "secondary": "#ff00ff",
            "accent": "#ffff00",
            "background": "#0a0a1a",
            "text": "#ffffff"
        }
    },
    "finance-business": {
        "component": "FinanceBusiness",
        "financeMotionStyle": "broadcast",
        "palette": {
            "primary": "#ffd700",
            "secondary": "#ffffff",
            "background": "#0a1929",
            "text": "#ffffff"
        }
    },
    "medical-lancet": {
        "component": "MedicalLancet",
        "financeMotionStyle": "editorial",
        "palette": {
            "primary": "#8b0000",
            "secondary": "#003366",
            "background": "#ffffff",
            "text": "#333333"
        }
    },
    "anime-light": {
        "component": "AnimeLight",
        "financeMotionStyle": "zen",
        "palette": {
            "primary": "#ffb3d9",
            "secondary": "#b3d9ff",
            "accent": "#ffffb3",
            "background": "#fff9f0",
            "text": "#4a4a4a"
        }
    }
}


def load_finance_motion_scenes(input_path: str) -> Dict[str, Any]:
    """加载 Finance Motion scenes.json"""
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_scene_to_remotion(scene: Dict[str, Any], style_config: Dict[str, Any]) -> Dict[str, Any]:
    """将单个 Finance Motion 场景转换为 Remotion 配置"""

    # 提取场景基本信息
    scene_id = scene.get('id', 'unknown')
    template = scene.get('template', 'unknown')
    duration_ms = scene.get('durationMs', 6000)

    # 转换动画配置
    animation = scene.get('animation', {})
    enter_animation = animation.get('enter', {})
    emphasis = animation.get('emphasis', {})

    # 提取数据
    data = scene.get('data', {})

    # 构建 Remotion props
    remotion_props = {
        "id": scene_id,
        "template": template,
        "durationInFrames": int(duration_ms / 1000 * 30),  # 假设 30fps
        "style": style_config,
        "animation": {
            "enter": {
                "type": enter_animation.get('type', 'fade'),
                "durationInFrames": int(enter_animation.get('durationMs', 1000) / 1000 * 30),
                "easing": enter_animation.get('easing', 'easeOutCubic')
            },
            "emphasis": {
                "atFrame": int(emphasis.get('atPct', 0.8) * duration_ms / 1000 * 30),
                "effect": emphasis.get('effect', 'pulse'),
                "target": emphasis.get('target', 'main')
            }
        },
        "data": data
    }

    return remotion_props


def convert_finance_motion_to_remotion(
    input_path: str,
    output_path: str,
    style: str = "claude-purple",
    fps: int = 30,
    width: int = 1080,
    height: int = 1920
) -> None:
    """
    主转换函数

    Args:
        input_path: Finance Motion scenes.json 路径
        output_path: 输出的 Remotion 配置文件路径
        style: 风格名称
        fps: 帧率
        width: 视频宽度
        height: 视频高度
    """

    # 验证风格
    if style not in TEMPLATE_MAPPING:
        raise ValueError(f"未知风格: {style}. 可用风格: {', '.join(TEMPLATE_MAPPING.keys())}")

    style_config = TEMPLATE_MAPPING[style]

    # 加载 Finance Motion 配置
    print(f"正在加载 Finance Motion 配置: {input_path}")
    finance_motion_data = load_finance_motion_scenes(input_path)

    # 提取场景列表
    scenes = finance_motion_data.get('scenes', [])
    print(f"找到 {len(scenes)} 个场景")

    # 转换每个场景
    remotion_compositions = []
    for i, scene in enumerate(scenes):
        print(f"转换场景 {i+1}/{len(scenes)}: {scene.get('id', 'unknown')}")
        remotion_props = convert_scene_to_remotion(scene, style_config)
        remotion_compositions.append(remotion_props)

    # 构建最终配置
    remotion_config = {
        "meta": {
            "generatedFrom": "finance-motion-8787",
            "sourceFile": input_path,
            "style": style,
            "generatedAt": finance_motion_data.get('meta', {}).get('liveData', {}).get('updatedAt', '')
        },
        "defaultProps": {
            "fps": fps,
            "width": width,
            "height": height,
            "component": style_config["component"],
            "palette": style_config["palette"]
        },
        "compositions": remotion_compositions
    }

    # 保存输出
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(remotion_config, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 转换完成！")
    print(f"输出文件: {output_path}")
    print(f"组合数量: {len(remotion_compositions)}")
    print(f"使用风格: {style} ({style_config['component']})")
    print(f"视频规格: {width}x{height} @ {fps}fps")


def main():
    parser = argparse.ArgumentParser(
        description="将 Finance Motion 8787 配置转换为 Remotion 配置"
    )

    parser.add_argument(
        '--input',
        required=True,
        help='Finance Motion scenes.json 路径'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='输出的 Remotion 配置文件路径'
    )

    parser.add_argument(
        '--style',
        default='claude-purple',
        choices=list(TEMPLATE_MAPPING.keys()),
        help='风格名称 (默认: claude-purple)'
    )

    parser.add_argument(
        '--fps',
        type=int,
        default=30,
        help='帧率 (默认: 30)'
    )

    parser.add_argument(
        '--width',
        type=int,
        default=1080,
        help='视频宽度 (默认: 1080)'
    )

    parser.add_argument(
        '--height',
        type=int,
        default=1920,
        help='视频高度 (默认: 1920)'
    )

    args = parser.parse_args()

    try:
        convert_finance_motion_to_remotion(
            input_path=args.input,
            output_path=args.output,
            style=args.style,
            fps=args.fps,
            width=args.width,
            height=args.height
        )
    except Exception as e:
        print(f"\n❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == '__main__':
    main()
