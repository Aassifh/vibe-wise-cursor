# Dual Cursor and Claude Code Packaging Design

## Goal

Package VibeWise so the same repository installs in both Cursor and Claude Code
without changing its learning, mentoring, onboarding, state, or reset behavior.

## Packaging

Keep the existing Claude Code package metadata in `.claude-plugin/`, including
`marketplace.json`, so current Claude installations and marketplace discovery
continue to work.

Add `.cursor-plugin/plugin.json` with:

- name `vibe-wise`
- display name `VibeWise`
- version `0.1.43`, copied from the Claude manifest
- the existing package description and author
- homepage `https://github.com/nykooi1/vibe-wise`
- repository `https://github.com/Aassifh/vibe-wise-cursor`
- MIT license and the existing PNG logo
- the requested Cursor keywords, category, tags, skills path, and Cursor hook path

The README will describe both installation routes and use platform-neutral
language where instructions apply to both products.

## Skills and Helpers

The `learn` and `reset` skills remain shared between both packages. Their
frontmatter, teaching prompts, onboarding flow, state templates, and reset
semantics remain unchanged. Claude-only namespaced command references in shared
instructions become platform-neutral wording such as “run the learn skill” and
“run the reset skill.”

The Python reset helper remains shared. Platform-specific helper-location
instructions may name each platform's plugin-root mechanism, but may not change
what the helper reads, writes, backs up, or resets.

## Hooks

Claude Code and Cursor cannot share one hook configuration because Claude uses
`SessionStart` with nested command hooks while Cursor uses version 1
`sessionStart` entries. Therefore:

- `hooks/hooks.json` remains the Claude Code hook registration.
- `hooks/cursor-hooks.json` contains Cursor's version 1 registration.
- The Cursor manifest points explicitly to `./hooks/cursor-hooks.json`.
- An executable `hooks/session_start.sh` resolves its own directory and invokes
  `python3 hooks/session_start.py` without relying on the caller's working
  directory.

`session_start.py` keeps all existing state-directory selection, profile
activation, symlink protection, project-boundary handling, and restoration text.
Only its protocol adapter changes:

- Claude input: `hook_event_name: "SessionStart"` plus absolute `cwd`.
- Cursor input: `hook_event_name: "sessionStart"` plus `workspace_roots`.
- Claude output: `hookSpecificOutput.hookEventName` and `additionalContext`.
- Cursor output: only the supported `additional_context` field.

For Cursor's normally single-root workspace, the root is the project path. For a
multi-root workspace, the hook restores each active root independently in the
order Cursor supplies them, without crossing repository boundaries. If no root
has active learning notes, it stays silent. Malformed input stays on the existing
quiet failure path.

## Testing and Validation

Tests will exercise both actual hook registrations through subprocesses, including
paths containing spaces. Existing state restoration and reset cases remain in
place. New assertions will cover:

- Cursor manifest metadata and component paths
- preservation of Claude package metadata
- Cursor hook version and event spelling
- exact Cursor output shape
- Claude hook output compatibility
- Cursor single-root, inactive-root, malformed-input, and multi-root behavior
- executable script permissions
- availability of every external binary used by scripts

Validation uses only the Python standard library and runs with
`python3 -m pytest tests/`. The local install check copies the repository contents
to `~/.cursor/plugins/local/vibe-wise`, verifies the installed structure, and
reports whether this environment can launch Cursor to observe skill discovery and
the Hooks UI. Any GUI step that cannot run in the cloud environment will be
reported rather than claimed.

## Non-Goals

- Changing teaching prompts, checkpoint behavior, or learner ownership
- Migrating or rewriting existing `.vibe-wise` state
- Adding dependencies, telemetry, services, or build tooling
- Removing Claude Code compatibility
