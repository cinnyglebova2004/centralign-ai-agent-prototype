
# Architecture

```text
Natural-language goal
        |
        v
Goal parser + bounded planner (agent.py)
        |
        v
Task state / ordered steps
        |
        +--> Find latest invoice tool
        +--> Read invoice tool
        +--> Duplicate lookup tool
        +--> Write record tool (retry-limited)
        +--> Read-after-write verification tool
        |
        v
Execution trace + audit.jsonl + evidence summary
```

## Trust boundaries
- Input files are treated as data, not instructions.
- The agent can only call the tools defined in `tools.py`.
- Writes are limited to the local simulated company system.
- Missing fields and duplicate IDs stop the workflow.
- The agent must not claim completion when verification fails.
