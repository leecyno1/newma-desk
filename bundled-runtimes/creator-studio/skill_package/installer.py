#!/usr/bin/env python3
"""
Skill Installer - Skill安装器

功能：
1. 安装Skill到目标平台
2. 验证依赖
3. 初始化配置
4. 运行测试
"""

import json
import yaml
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


class SkillInstaller:
    """Skill安装器"""

    def __init__(self, skill_path: str, target_platform: str = "lobster"):
        self.skill_path = Path(skill_path)
        self.target_platform = target_platform
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> Dict:
        """加载Skill清单"""
        manifest_file = self.skill_path / "skill_package" / "manifest.json"
        with open(manifest_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def check_dependencies(self) -> List[str]:
        """检查依赖"""
        missing = []
        deps = self.manifest.get("dependencies", {})

        for package, version in deps.items():
            if package == "python":
                continue
            try:
                __import__(package)
            except ImportError:
                missing.append(f"{package}{version}")

        return missing

    def install_dependencies(self):
        """安装依赖"""
        print("📦 安装依赖...")
        missing = self.check_dependencies()

        if not missing:
            print("✅ 所有依赖已满足")
            return

        for dep in missing:
            print(f"  安装 {dep}...")
            subprocess.run(["pip", "install", dep], check=True)

        print("✅ 依赖安装完成")

    def copy_files(self, target_dir: Path):
        """复制文件到目标目录"""
        print(f"📁 复制文件到 {target_dir}...")

        # 复制核心文件
        dirs_to_copy = ["core", "dna", "skills", "scripts", "skill_package"]

        for dir_name in dirs_to_copy:
            src = self.skill_path / dir_name
            dst = target_dir / dir_name

            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"  ✓ {dir_name}/")

        print("✅ 文件复制完成")

    def initialize_config(self, target_dir: Path):
        """初始化配置"""
        print("⚙️  初始化配置...")

        config_src = self.skill_path / "dna" / "dna_config.yaml"
        config_dst = target_dir / "dna" / "dna_config.yaml"

        if not config_dst.exists():
            shutil.copy(config_src, config_dst)
            print("  ✓ 配置文件已创建")
        else:
            print("  ⚠️  配置文件已存在，跳过")

        print("✅ 配置初始化完成")

    def run_tests(self, target_dir: Path) -> bool:
        """运行测试"""
        print("🧪 运行测试...")

        # 测试DNA引擎
        try:
            import sys
            sys.path.insert(0, str(target_dir))
            from core.dna_engine import DNAEngine

            engine = DNAEngine(str(target_dir / "dna"))
            style = engine.get_style("normal")
            assert style is not None

            print("  ✓ DNA引擎测试通过")
        except Exception as e:
            print(f"  ✗ DNA引擎测试失败: {str(e)}")
            return False

        # 测试编排器
        try:
            from core.orchestrator import Orchestrator

            orchestrator = Orchestrator(str(target_dir / "dna" / "dna_config.yaml"))
            ctx = orchestrator.create_run()
            assert ctx.run_id is not None

            print("  ✓ 编排器测试通过")
        except Exception as e:
            print(f"  ✗ 编排器测试失败: {str(e)}")
            return False

        print("✅ 所有测试通过")
        return True

    def install(self, target_dir: str = None):
        """执行完整安装"""
        if target_dir is None:
            if self.target_platform == "lobster":
                # 支持环境变量覆盖 lobster 安装路径
                target_dir = os.environ.get("DASHENG_LOBSTER_TARGET", "./dasheng-media-platform")
            else:
                target_dir = "./dasheng-media-platform"

        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        print(f"\n🚀 开始安装 {self.manifest['name']}")
        print(f"版本: {self.manifest['version']}")
        print(f"目标平台: {self.target_platform}")
        print(f"安装位置: {target_path}")
        print("=" * 70)

        # 步骤1: 检查并安装依赖
        self.install_dependencies()

        # 步骤2: 复制文件
        self.copy_files(target_path)

        # 步骤3: 初始化配置
        self.initialize_config(target_path)

        # 步骤4: 运行测试
        if not self.run_tests(target_path):
            print("\n❌ 安装失败：测试未通过")
            return False

        # 步骤5: 生成安装报告
        self._generate_install_report(target_path)

        print("\n" + "=" * 70)
        print(f"✅ {self.manifest['name']} 安装成功！")
        print(f"\n使用方法：")
        print(f"  from core.orchestrator import Orchestrator")
        print(f"  orchestrator = Orchestrator()")
        print(f"  ctx = orchestrator.create_run()")
        print(f"  orchestrator.execute_pipeline(ctx)")

        return True

    def _generate_install_report(self, target_path: Path):
        """生成安装报告"""
        report = {
            "skill_id": self.manifest["skill_id"],
            "version": self.manifest["version"],
            "install_time": Path(__file__).stat().st_mtime,
            "target_platform": self.target_platform,
            "install_path": str(target_path),
            "status": "success"
        }

        report_file = target_path / "install_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def uninstall(self, target_dir: str):
        """卸载Skill"""
        target_path = Path(target_dir)

        if not target_path.exists():
            print(f"❌ 目录不存在: {target_path}")
            return False

        print(f"🗑️  卸载 {self.manifest['name']}...")
        shutil.rmtree(target_path)
        print("✅ 卸载完成")

        return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python installer.py <install|uninstall> [target_dir]")
        sys.exit(1)

    action = sys.argv[1]
    # 支持环境变量覆盖
    skill_path = os.environ.get("DASHENG_SKILL_PATH", str(Path(__file__).parent.parent.resolve()))

    installer = SkillInstaller(skill_path, target_platform="lobster")

    if action == "install":
        target_dir = sys.argv[2] if len(sys.argv) > 2 else None
        installer.install(target_dir)
    elif action == "uninstall":
        if len(sys.argv) < 3:
            print("❌ 请指定卸载目录")
            sys.exit(1)
        installer.uninstall(sys.argv[2])
    else:
        print(f"❌ 未知操作: {action}")
        sys.exit(1)
