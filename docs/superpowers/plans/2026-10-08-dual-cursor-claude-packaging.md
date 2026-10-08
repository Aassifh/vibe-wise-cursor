# Dual Cursor and Claude Code Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one VibeWise repository installable in Cursor and Claude Code while preserving all learning and state behavior.

**Architecture:** Keep Claude's existing manifest and hook registration, add a Cursor manifest and Cursor-specific hook registration, and share the skills and Python implementation. `session_start.py` will normalize each platform's input into project roots and serialize the unchanged restoration context in that platform's output envelope.

**Tech Stack:** JSON manifests, Markdown skills and documentation, POSIX shell, Python 3 standard library, pytest

## Global Constraints

- Code and comments must be in English.
- Do not alter learning, mentoring, onboarding, checkpoint, reset, or state-template behavior.
- Add no Python or system dependencies.
- Preserve `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- Use `https://github.com/Aassifh/vibe-wise-cursor` as the Cursor manifest repository.
- Every script must be executable and every external binary it invokes must exist.

---

### Task 1: Cursor Package Metadata

**Files:**
- Create: `.cursor-plugin/plugin.json`
- Create: `tests/test_packaging.py`

**Interfaces:**
- Consumes: version, description, and author from `.claude-plugin/plugin.json`
- Produces: a Cursor plugin manifest that discovers `./skills/` and `./hooks/cursor-hooks.json`

- [ ] **Step 1: Write the failing package tests**

```python
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cursor_manifest_has_expected_metadata_and_components():
    source = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    manifest = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
    assert manifest == {
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
    }


def test_both_plugin_formats_and_shared_assets_exist():
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
    assert all((ROOT / path).is_file() for path in required)
```

- [ ] **Step 2: Run the tests and confirm the missing manifest fails**

Run: `python3 -m pytest tests/test_packaging.py -q`

Expected: FAIL because `.cursor-plugin/plugin.json` does not exist.

- [ ] **Step 3: Add the Cursor manifest**

```json
{
  "name": "vibe-wise",
  "displayName": "VibeWise",
  "version": "0.1.43",
  "description": "You build. AI writes. Learn how to build software while Claude writes the code.",
  "author": { "name": "Noah Kim", "email": "" },
  "homepage": "https://github.com/nykooi1/vibe-wise",
  "repository": "https://github.com/Aassifh/vibe-wise-cursor",
  "license": "MIT",
  "logo": "assets/vibewise-icon.png",
  "keywords": ["learning", "mentoring", "planning"],
  "category": "developer-tools",
  "tags": ["learning", "guidance"],
  "skills": "./skills/",
  "hooks": "./hooks/cursor-hooks.json"
}
```

- [ ] **Step 4: Run the package tests**

Run: `python3 -m pytest tests/test_packaging.py -q`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add .cursor-plugin/plugin.json tests/test_packaging.py
git commit -m "feat: add Cursor plugin manifest"
```

### Task 2: Dual Hook Protocol

**Files:**
- Create: `hooks/cursor-hooks.json`
- Create: `hooks/session_start.sh`
- Modify: `hooks/session_start.py`
- Modify: `tests/test_session_start.py`
- Modify: `tests/test_reset.py`

**Interfaces:**
- Consumes: Claude `{hook_event_name: "SessionStart", cwd}` or Cursor `{hook_event_name: "sessionStart", workspace_roots}`
- Produces: Claude `hookSpecificOutput.additionalContext` or Cursor `additional_context`
- Preserves: `state_directory(Path) -> Path | None` for `skills/reset/reset.py`

- [ ] **Step 1: Update hook tests first**

Change the test harness to load both registrations, invoke the Cursor wrapper as
an argument list, and provide separate payload builders:

```python
CLAUDE_CONFIG = json.loads((ROOT / "hooks/hooks.json").read_text())
CURSOR_CONFIG = json.loads((ROOT / "hooks/cursor-hooks.json").read_text())
CLAUDE_REGISTRATION = CLAUDE_CONFIG["hooks"]["SessionStart"][0]
CURSOR_REGISTRATION = CURSOR_CONFIG["hooks"]["sessionStart"][0]

def cursor_payload(*roots):
    return json.dumps({
        "hook_event_name": "sessionStart",
        "workspace_roots": [str(root) for root in roots],
        "session_id": "test-session",
        "is_background_agent": False,
    })
```

Add assertions that the Cursor config equals:

```python
{
    "version": 1,
    "hooks": {
        "sessionStart": [{"command": "./hooks/session_start.sh"}],
    },
}
```

Add Cursor subprocess cases asserting active state emits exactly one key named
`additional_context`, inactive state emits no stdout, malformed or relative roots
emit no stdout, and two active workspace roots both appear in the context. Keep
all current Claude cases and assert their existing output shape.

Update the reset integration assertion to continue sending Claude input and
checking Claude output, proving the reset helper's integration is unchanged.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `python3 -m pytest tests/test_session_start.py tests/test_reset.py -q`

Expected: FAIL because the Cursor hook config and wrapper do not exist and the
Python hook does not understand Cursor input.

- [ ] **Step 3: Add the Cursor hook registration**

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      { "command": "./hooks/session_start.sh" }
    ]
  }
}
```

- [ ] **Step 4: Add the wrapper**

```sh
#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/session_start.py"
```

Run: `chmod +x hooks/session_start.sh`

- [ ] **Step 5: Implement protocol normalization**

Retain `profile_is_active`, `state_directory`, and the restoration text. Split
the adapter into:

```python
def project_roots(payload):
    event = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if event == "SessionStart":
        candidates = [payload.get("cwd")]
    elif event == "sessionStart":
        candidates = payload.get("workspace_roots")
        if not isinstance(candidates, list):
            return event, []
    else:
        return event, []
    roots = []
    for candidate in candidates:
        if not isinstance(candidate, str) or not Path(candidate).is_absolute():
            continue
        root = Path(candidate).resolve()
        if root.is_dir():
            roots.append(root)
    return event, roots
```

Build one unchanged restoration block per active root. Return:

```python
if event == "SessionStart":
    return {"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }}
if event == "sessionStart":
    return {"additional_context": context}
```

Join multiple Cursor root blocks with `"\n\n"` and remain silent when none are
active. Update only protocol-related docstrings and comments from Claude-specific
to platform-neutral wording.

- [ ] **Step 6: Run focused tests**

Run: `python3 -m pytest tests/test_session_start.py tests/test_reset.py -q`

Expected: all hook and reset tests pass.

- [ ] **Step 7: Commit**

```bash
git add hooks/cursor-hooks.json hooks/session_start.sh hooks/session_start.py tests/test_session_start.py tests/test_reset.py
git commit -m "feat: support Cursor session start hooks"
```

### Task 3: Shared Skill Instructions and Dual-Platform README

**Files:**
- Modify: `skills/learn/SKILL.md`
- Modify: `skills/reset/SKILL.md`
- Modify: `README.md`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: the same learn and reset skills from both manifests
- Produces: platform-neutral skill invocation language and installation guidance for both products

- [ ] **Step 1: Add failing content checks**

```python
def test_shared_skills_do_not_require_claude_namespaced_commands():
    skill_text = "\n".join(
        (ROOT / path).read_text()
        for path in ("skills/learn/SKILL.md", "skills/reset/SKILL.md")
    )
    assert "/vibe-wise:learn" not in skill_text
    assert "/vibe-wise:reset" not in skill_text


def test_readme_documents_cursor_and_claude_installation():
    readme = (ROOT / "README.md").read_text()
    assert "~/.cursor/plugins/local/vibe-wise" in readme
    assert "Claude Code" in readme
    assert ".cursor-plugin/plugin.json" in readme
```

- [ ] **Step 2: Run the content tests and confirm failure**

Run: `python3 -m pytest tests/test_packaging.py -q`

Expected: FAIL because the reset skill still names `/vibe-wise:learn` and the
README does not document Cursor installation.

- [ ] **Step 3: Make shared skill wording platform-neutral**

Replace command references only:

- `/vibe-wise:learn` → `run the learn skill`
- `/vibe-wise:reset` → `run the reset skill`

Retain all teaching instructions and state templates byte-for-byte otherwise.
Where the reset helper command needs a plugin root, show a Claude command using
`${CLAUDE_PLUGIN_ROOT}` and a Cursor command using `${CURSOR_PLUGIN_ROOT}`, with
the same Python arguments and confirmation flow.

- [ ] **Step 4: Rewrite packaging sections of the README**

Keep the product explanation and learning example. Change the introduction to
describe VibeWise as an AI coding plugin. Add separate Cursor and Claude Code
installation subsections. The Cursor subsection must include:

```sh
mkdir -p ~/.cursor/plugins/local
cp -R /absolute/path/to/vibe-wise-cursor ~/.cursor/plugins/local/vibe-wise
```

Then instruct users to restart Cursor, confirm both skills in the skills list,
and inspect Cursor Settings → Hooks and the Hooks output channel for
`sessionStart`. Retain Claude marketplace instructions and namespaced invocation
examples only in the Claude-specific installation section.

- [ ] **Step 5: Run package tests**

Run: `python3 -m pytest tests/test_packaging.py -q`

Expected: all package tests pass.

- [ ] **Step 6: Commit**

```bash
git add README.md skills/learn/SKILL.md skills/reset/SKILL.md tests/test_packaging.py
git commit -m "docs: explain dual-platform plugin usage"
```

### Task 4: Full Verification and Local Cursor Installation

**Files:**
- Modify only if a failing verification exposes a defect in files from Tasks 1–3

**Interfaces:**
- Consumes: completed dual-platform package
- Produces: verified repository and local Cursor plugin copy

- [ ] **Step 1: Verify setup completed before testing**

Read `/tmp/cursor/async-install/install-user.status` when present. If setup is
still running, wait for that process without killing it.

- [ ] **Step 2: Run the complete suite**

Run: `python3 -m pytest tests/`

Expected: all tests pass with no warnings or errors.

- [ ] **Step 3: Verify scripts and binaries**

Run:

```bash
test -x hooks/session_start.sh
test -x hooks/session_start.py
test -x skills/reset/reset.py
command -v python3
command -v dirname
```

Expected: every command exits 0 and `python3` resolves to an absolute executable.
If the existing Python files are not executable, run:

```bash
chmod +x hooks/session_start.py skills/reset/reset.py
```

and ensure each has a valid Python 3 shebang.

- [ ] **Step 4: Install a clean local Cursor copy**

Run:

```bash
rm -rf ~/.cursor/plugins/local/vibe-wise
mkdir -p ~/.cursor/plugins/local/vibe-wise
git archive HEAD | tar -x -C ~/.cursor/plugins/local/vibe-wise
```

Verify the copied manifest, skills, hooks, assets, README, LICENSE, and tests.
Do not include `.git`, caches, or learner state.

- [ ] **Step 5: Perform available Cursor runtime validation**

If Cursor Desktop is available, restart it and confirm:

- `learn` and `reset` appear in the skills list.
- `sessionStart` appears in Cursor Settings → Hooks.
- Starting a conversation in a test project with an active `.vibe-wise/profile.md`
  produces hook output and injects restoration context.

If Cursor Desktop is unavailable, report that limitation and provide the automated
manifest, subprocess, and installed-layout evidence without claiming GUI success.

- [ ] **Step 6: Commit verification fixes, if any**

```bash
git add .cursor-plugin hooks skills tests README.md
git commit -m "fix: complete dual-platform packaging verification"
```

Skip this commit when verification required no changes.

- [ ] **Step 7: Push the branch**

Run: `git push -u origin cursor/dual-plugin-packaging-8f9b`

Expected: branch is up to date on the fork.
