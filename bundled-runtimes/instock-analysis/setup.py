"""Include the canonical Desk descriptor in wheels without a second source copy."""

import json
import runpy
from pathlib import Path
from shutil import copyfile

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent
source_release = runpy.run_path(str(ROOT / "build_release.py"))["source_release"]


class BuildRuntime(build_py):
    def run(self):
        release = source_release(ROOT, self.distribution.get_version())
        super().run()
        source = Path(__file__).parent / "integrations/newma-desk/instock-suite/suite.json"
        target = Path(self.build_lib) / "instock/web/_suite.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, target)
        (Path(self.build_lib) / "instock/_release.json").write_text(json.dumps(release), "utf-8")


class SourceRuntime(sdist):
    def make_release_tree(self, base_dir, files):
        release = source_release(ROOT, self.distribution.get_version())
        super().make_release_tree(base_dir, files)
        (Path(base_dir) / "instock/_release.json").write_text(json.dumps(release), "utf-8")


setup(cmdclass={"build_py": BuildRuntime, "sdist": SourceRuntime})
