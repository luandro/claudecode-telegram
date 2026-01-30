@AGENTS.md

## Codex workflow
Before implementation, call `codex` with a `sessionId` to plan. Follow the plan. After implementation, call `codex` again with the same `sessionId` to review.
Use `resetSession: true` to start a brand-new task. Use higher `reasoningEffort` for reviews when needed.
