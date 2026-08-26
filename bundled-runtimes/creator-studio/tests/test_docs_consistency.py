import sys
import unittest
import re
from pathlib import Path


# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from path_config import get_project_root

ROOT = get_project_root()


class DocsConsistencyTests(unittest.TestCase):
    def test_stage_interfaces_doc_exists_and_is_referenced(self):
        doc = ROOT / "docs" / "STAGE_INTERFACES.md"
        self.assertTrue(doc.exists())

        for target in [
            ROOT / "README.md",
            ROOT / "docs" / "INSTALLATION.md",
            ROOT / "skills" / "dasheng-media-sop" / "SKILL.md",
        ]:
            content = target.read_text(encoding="utf-8")
            self.assertIn("docs/STAGE_INTERFACES.md", content)

    def test_root_install_files_exist(self):
        for target in [
            ROOT / ".gitignore",
            ROOT / "requirements.txt",
            ROOT / "ENV_TEMPLATE.env",
            ROOT / "install_to_openclaw.sh",
            ROOT / "install_to_hermes.sh",
        ]:
            self.assertTrue(target.exists(), msg=str(target))

    def test_readme_local_markdown_links_resolve(self):
        readme = ROOT / "README.md"
        content = readme.read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)#][^)]+)\)", content)
        for link in links:
            if "://" in link or link.startswith("mailto:"):
                continue
            target = (ROOT / link).resolve()
            self.assertTrue(target.exists(), msg=f"README link target missing: {link}")

    def test_documented_mainline_doctor_selects_a_run(self):
        for target in [ROOT / "README.md", ROOT / "docs" / "ONBOARDING.md"]:
            content = target.read_text(encoding="utf-8")
            self.assertNotIn("run_mainline_stage.py doctor --strict", content)
            self.assertIn("run_mainline_stage.py doctor --latest --strict", content)


if __name__ == "__main__":
    unittest.main()
