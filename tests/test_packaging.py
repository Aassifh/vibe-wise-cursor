"""Validate the shared Claude Code and Cursor plugin package."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_cursor_manifest_has_expected_metadata_and_components(self):
        source = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        manifest = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        self.assertEqual(manifest, {
            "name": "vibe-wise",
            "displayName": "VibeWise",
            "version": source["version"],
            "description": source["description"],
            "author": {"name": source["author"]["name"], "email": ""},
            "homepage": "https://github.com/nykooi1/vibe-wise",
            "repository": "https://github.com/Aassifh/vibe-wise-cursor",
            "license": "MIT",
            "logo": "assets/vibewise-icon.png",
            "keywords": ["learning", "mentoring", "planning"],
            "category": "developer-tools",
            "tags": ["learning", "guidance"],
            "skills": "./skills/",
            "hooks": "./hooks/cursor-hooks.json",
        })

    def test_both_plugin_formats_and_shared_assets_exist(self):
        required = (
            ".claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            ".cursor-plugin/plugin.json",
            "skills/learn/SKILL.md",
            "skills/reset/SKILL.md",
            "assets/vibewise-icon.png",
            "README.md",
            "LICENSE",
        )
        self.assertTrue(all((ROOT / path).is_file() for path in required))

    def test_shared_skills_do_not_require_claude_namespaced_commands(self):
        skill_text = "\n".join(
            (ROOT / path).read_text()
            for path in ("skills/learn/SKILL.md", "skills/reset/SKILL.md")
        )
        self.assertNotIn("/vibe-wise:learn", skill_text)
        self.assertNotIn("/vibe-wise:reset", skill_text)

    def test_readme_documents_cursor_and_claude_installation(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("~/.cursor/plugins/local/vibe-wise", readme)
        self.assertIn("Claude Code", readme)
        self.assertIn(".cursor-plugin/plugin.json", readme)


if __name__ == "__main__":
    unittest.main()
