"""Exercise the actual hook command in isolated new and existing projects."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_CONFIG = json.loads((ROOT / "hooks/hooks.json").read_text())
CURSOR_CONFIG = json.loads((ROOT / "hooks/cursor-hooks.json").read_text())
REGISTRATION = CLAUDE_CONFIG["hooks"]["SessionStart"][0]
CURSOR_REGISTRATION = CURSOR_CONFIG["hooks"]["sessionStart"][0]


class SessionStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vibe-wise-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        (self.project / ".git").mkdir()

    def state(self, project=None, mode="active"):
        directory = (project or self.project) / ".vibe-wise"
        directory.mkdir()
        (directory / "profile.md").write_text(
            f"# Learner Profile\nLearning mode: {mode}\nOnboarding: complete\n"
            "Checkpoint frequency: Light\nQuestion style: Open-ended\n"
            "Implementation style: AI writes code\n"
            "Strong concepts: HTTP request flow\n", encoding="utf-8"
        )
        (directory / "project-map.md").write_text(
            "# Project Map\nCLI → service.py → SQLite\n", encoding="utf-8"
        )
        (directory / "progress.md").write_text(
            "# Learning Progress\n## Transactions\n"
            "Demonstrated understanding: two writes must succeed together.\n"
            "## Queues\nNeeds reinforcement: retries.\n", encoding="utf-8"
        )
        return directory

    def run_hook(self, cwd=None, source="startup", raw=None):
        payload = raw if raw is not None else json.dumps({
            "hook_event_name": "SessionStart", "source": source,
            "cwd": str(cwd or self.project),
        })
        result = subprocess.run(
            REGISTRATION["hooks"][0]["command"], shell=True,
            input=payload, text=True, capture_output=True, timeout=5,
            # The hook needs a Python executable and its plugin location, not the
            # developer's credentials or unrelated environment configuration.
            env={
                "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.defpath)),
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
            }, cwd=self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout) if result.stdout else None

    def context(self, **kwargs):
        result = self.run_hook(**kwargs)["hookSpecificOutput"]
        self.assertEqual(result["hookEventName"], "SessionStart")
        return result["additionalContext"]

    def run_cursor_hook(self, roots=None, raw=None):
        payload = raw if raw is not None else json.dumps({
            "hook_event_name": "sessionStart",
            "workspace_roots": [
                str(root) for root in (roots if roots is not None else [self.project])
            ],
            "session_id": "test-session",
            "is_background_agent": False,
        })
        result = subprocess.run(
            [str(ROOT / CURSOR_REGISTRATION["command"])],
            input=payload, text=True, capture_output=True, timeout=5,
            env={"PATH": os.pathsep.join((str(Path(sys.executable).parent), os.defpath))},
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout) if result.stdout else None

    def test_cursor_registration_uses_version_one_session_start(self):
        self.assertEqual(CURSOR_CONFIG, {
            "version": 1,
            "hooks": {
                "sessionStart": [{"command": "./hooks/session_start.sh"}],
            },
        })

    def test_cursor_active_project_uses_only_supported_output_field(self):
        self.state()
        result = self.run_cursor_hook()
        self.assertEqual(set(result), {"additional_context"})
        self.assertIn(str(ROOT / "skills/learn/SKILL.md"),
                      result["additional_context"])
        self.assertIn(str(self.project / ".vibe-wise"),
                      result["additional_context"])

    def test_cursor_inactive_and_malformed_projects_write_nothing(self):
        self.assertIsNone(self.run_cursor_hook())
        malformed = (
            "",
            "{",
            "[]",
            "null",
            '{"hook_event_name":"sessionStart"}',
            '{"hook_event_name":"sessionStart","workspace_roots":"not-a-list"}',
            '{"hook_event_name":"sessionStart","workspace_roots":["relative"]}',
        )
        for raw in malformed:
            with self.subTest(raw=raw):
                self.assertIsNone(self.run_cursor_hook(raw=raw))

    def test_cursor_restores_each_active_root_in_multi_root_workspace(self):
        self.state()
        second = self.root / "second project"
        second.mkdir()
        (second / ".git").mkdir()
        self.state(second)
        context = self.run_cursor_hook(
            roots=[self.project, second])["additional_context"]
        self.assertIn(str(self.project / ".vibe-wise"), context)
        self.assertIn(str(second / ".vibe-wise"), context)

    def test_cursor_skips_symlink_loop_and_restores_other_roots(self):
        self.state()
        first = self.root / "loop-one"
        second = self.root / "loop-two"
        first.symlink_to(second)
        second.symlink_to(first)
        context = self.run_cursor_hook(
            roots=[first, self.project])["additional_context"]
        self.assertIn(str(self.project / ".vibe-wise"), context)

    def test_fresh_project_is_inactive_and_hook_writes_nothing(self):
        self.assertIsNone(self.run_hook())
        self.assertEqual(list(self.project.iterdir()), [self.project / ".git"])

    def test_restore_all_registered_session_lifecycles(self):
        self.state()
        for source in ("startup", "resume", "clear", "compact", "fork"):
            with self.subTest(source=source):
                self.assertTrue(re.fullmatch(REGISTRATION["matcher"], source))
                context = self.context(source=source)
                self.assertIn(str(ROOT / "skills/learn/SKILL.md"), context)
                self.assertIn(str(self.project / ".vibe-wise"), context)
                self.assertIn("Read profile.md and project-map.md", context)
                self.assertIn("Search the entire progress.md", context)
                self.assertNotIn("Checkpoint frequency: Light", context)
                self.assertNotIn("two writes must succeed together", context)

    def test_existing_repo_restores_from_nested_working_directory(self):
        self.state()
        nested = self.project / "src" / "services"
        nested.mkdir(parents=True)
        (nested / "service.py").write_text("def run():\n    return 'ok'\n")
        self.assertIn(str(self.project / ".vibe-wise"), self.context(cwd=nested))

    def test_no_git_project_restores(self):
        project = self.root / "fresh-no-git"
        project.mkdir()
        self.state(project)
        self.assertIn(str(project / ".vibe-wise"), self.context(cwd=project))

    def test_legacy_notes_restore_without_migration(self):
        state = self.state()
        legacy = state.with_name(".sensible-vibes")
        state.rename(legacy)
        before = {p.name: p.read_bytes() for p in legacy.iterdir()}
        context = self.context(source="compact")
        self.assertIn("VibeWise is active", context)
        self.assertIn(str(legacy), context)
        self.assertIn("Read profile.md and project-map.md", context)
        self.assertFalse(state.exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in legacy.iterdir()})

    def test_new_notes_take_precedence_over_legacy_at_same_location(self):
        self.state().rename(self.project / ".sensible-vibes")
        self.state(mode="paused")
        self.assertIsNone(self.run_hook())

    def test_nearest_legacy_notes_take_precedence_over_parent_notes(self):
        self.state()
        child = self.project / "package"
        child.mkdir()
        self.state(child, mode="paused").rename(child / ".sensible-vibes")
        self.assertIsNone(self.run_hook(cwd=child))

    def test_legacy_notes_respect_worktree_boundary(self):
        self.state().rename(self.project / ".sensible-vibes")
        child = self.project / "worktree"
        child.mkdir()
        (child / ".git").write_text("gitdir: /another/repo/.git/worktrees/test")
        self.assertIsNone(self.run_hook(cwd=child))

    def test_symlinked_new_state_does_not_fall_back_to_legacy(self):
        self.state().rename(self.project / ".sensible-vibes")
        (self.project / ".vibe-wise").symlink_to(self.root / "missing", target_is_directory=True)
        self.assertIsNone(self.run_hook())

    def test_nested_repository_and_worktree_do_not_borrow_parent_profile(self):
        self.state()
        for name, git_is_file in (("nested-repo", False), ("worktree", True)):
            child = self.project / name
            child.mkdir()
            if git_is_file:
                (child / ".git").write_text("gitdir: /some/other/repo/.git/worktrees/test")
            else:
                (child / ".git").mkdir()
            self.assertIsNone(self.run_hook(cwd=child))

    def test_nearest_state_wins(self):
        self.state()
        child = self.project / "package"
        child.mkdir()
        self.state(child, mode="paused")
        self.assertIsNone(self.run_hook(cwd=child))

    def test_paused_state_is_not_reactivated_by_compaction(self):
        self.state(mode="paused")
        self.assertIsNone(self.run_hook(source="compact"))

    def test_incomplete_onboarding_survives_restart(self):
        state = self.state()
        (state / "profile.md").write_text(
            "Learning mode: active\nOnboarding: incomplete\n"
            "Remaining onboarding: stack familiarity\n"
        )
        context = self.context()
        self.assertIn(str(state), context)
        self.assertIn("If onboarding is incomplete", context)
        self.assertIn("ask only unanswered questions", context)

    def test_missing_map_and_progress_do_not_discard_preferences(self):
        state = self.state()
        (state / "project-map.md").unlink()
        (state / "progress.md").unlink()
        context = self.context()
        self.assertIn(str(state), context)
        self.assertIn("Discover optional files before reading", context)
        self.assertIn("Recreate missing notes only from evidence", context)

    def test_large_notes_do_not_change_bootstrap_or_hide_pending_restore(self):
        state = self.state()
        before = self.context(source="compact")
        with (state / "profile.md").open("a") as stream:
            stream.write("a" * 100000)
        (state / "project-map.md").write_text("b" * 100000)
        (state / "progress.md").write_text(
            "## Earlier learning\n" + "Older summary.\n" * 10000 +
            "## Pending decision\nAwaiting approval to implement SQLite.\n"
        )
        context = self.context(source="compact")
        self.assertLess(len(context), 10000)
        self.assertEqual(context, before)
        self.assertIn("Search the entire progress.md", context)
        self.assertIn("read their complete sections", context)
        self.assertNotIn("Earlier learning", context)
        self.assertNotIn("SQLite", context)

    def test_paused_mode_beyond_old_profile_cutoff_is_respected(self):
        state = self.state()
        (state / "profile.md").write_text(
            "# Profile\n" + "Older preference.\n" * 1000 + "Learning mode: paused\n"
        )
        self.assertIsNone(self.run_hook(source="compact"))

    def test_legacy_profile_without_mode_still_restores(self):
        state = self.state()
        (state / "profile.md").write_text("# Learner Profile\nExperience: Beginner\n")
        self.assertIn(str(state), self.context())

    def test_malformed_inputs_exit_cleanly(self):
        for raw in ("", "{", "[]", "null", "42", '{"cwd": 4}',
                    '{"hook_event_name":"SessionStart","cwd":"relative"}'):
            with self.subTest(raw=raw):
                self.assertIsNone(self.run_hook(raw=raw))

    def test_unreadable_or_empty_profile_does_not_activate(self):
        state = self.state()
        for content in (b"", b" \n\t", b"\xff\xfe"):
            (state / "profile.md").write_bytes(content)
            self.assertIsNone(self.run_hook())

    def test_symlinked_profile_is_not_read(self):
        state = self.state()
        outside = self.root / "outside.md"
        outside.write_text("Learning mode: active\nPRIVATE")
        (state / "profile.md").unlink()
        (state / "profile.md").symlink_to(outside)
        self.assertIsNone(self.run_hook())

    def test_symlinked_state_directory_is_not_read(self):
        state = self.state()
        alternate = self.root / "alternate"
        alternate.mkdir()
        (alternate / ".vibe-wise").symlink_to(state, target_is_directory=True)
        self.assertIsNone(self.run_hook(cwd=alternate))

    def test_hook_never_changes_state(self):
        state = self.state()
        before = {p.name: p.read_bytes() for p in state.iterdir()}
        self.run_hook(source="compact")
        after = {p.name: p.read_bytes() for p in state.iterdir()}
        self.assertEqual(before, after)

    def test_compaction_points_to_pending_decision_without_inventing_approval(self):
        state = self.state()
        with (state / "progress.md").open("a") as stream:
            stream.write("## Pending decision\nUse SQLite. Awaiting Implement or a question.\n"
                         "- Pending decision: JSON storage; waiting for Implement.\n")
        context = self.context(source="compact")
        self.assertIn("Search the entire progress.md for pending decisions", context)
        self.assertIn("before coding", context)
        self.assertIn("await implementation approval", context)
        self.assertIn("Restarting or compacting is not approval", context)
        self.assertNotIn("Use SQLite", context)
        self.assertNotIn("JSON storage", context)


if __name__ == "__main__":
    unittest.main()
