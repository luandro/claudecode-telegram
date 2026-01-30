# Repository Guidelines

## Project Structure & Module Organization
- `bridge.py` contains the Telegram webhook bridge and tmux integration.
- `hooks/send-to-telegram.sh` is the Claude Code Stop hook that parses transcripts and replies via Telegram.
- `README.md` documents setup, commands, and environment variables.
- `demo.gif` is the demo asset.
- Packaging metadata lives in `pyproject.toml` and `claudecode_telegram.egg-info/`.

## Build, Test, and Development Commands
- `uv venv && source .venv/bin/activate`: create and activate the Python virtual environment.
- `uv pip install -e .`: install the project in editable mode.
- `python bridge.py`: run the bridge server locally.
- `claudecode-telegram`: console script entry point (same as `bridge.py`).
- `cloudflared tunnel --url http://localhost:8080`: expose the local bridge for Telegram webhooks.
- `tmux new -s claude` and `claude --dangerously-skip-permissions`: keep Claude Code running in a tmux session for message injection.

## Coding Style & Naming Conventions
- Python: follow the existing style in `bridge.py` (4-space indentation, descriptive function/variable names).
- Shell: keep POSIX/Bash-compatible syntax like `hooks/send-to-telegram.sh` (explicit `#!/bin/bash`).
- Prefer small, readable helpers over large monolithic functions; match naming and layout already in the file you touch.

## Testing Guidelines
- No automated test suite is configured. If you add tests, document how to run them in this file and `README.md`.
- Manual checks: verify webhook receipt, tmux injection, and Telegram reply flow end-to-end.

## Commit & Pull Request Guidelines
- Commit messages in history follow a short, sentence-style or Conventional Commits pattern (e.g., `feat: ...`, `Add ...`). Keep them concise and scoped.
- PRs should include a brief summary, setup/run steps if behavior changes, and any new environment variables.
- If you modify the hook or message formatting, include a short sample transcript in the PR description.

## Security & Configuration Tips
- Keep `TELEGRAM_BOT_TOKEN` out of version control; pass via environment variable or local config.
- Update `~/.claude/hooks/send-to-telegram.sh` and `~/.claude/settings.json` locally; do not commit user-specific tokens or paths.
