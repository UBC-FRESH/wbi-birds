# ws3 agent capability backend (lab recipe)

The ws3 agent capabilities (`ws3_hint`, `rtfm`, `build_mask`, ...) run against an
OpenAI-compatible endpoint. For this lab we point them at the OpenCode Go gateway
using the same session credential as the coding session.

## Requirements

- `pip install "ws3[agent]"` (installs `fresh-agent-core`)
- An OpenAI-compatible endpoint + credential. For OpenCode Go:
  - endpoint: `https://opencode.ai/zen/go/v1`
  - model: e.g. `deepseek-v4.1-flash`
  - header: `x-opencode-session: <session id>` (required by the gateway)
  - bearer token: the `opencode-go` credential

## Two gotchas

- The gateway returns `MissingSessionID` without the session header.
- Reasoning models spend tokens in `reasoning_content`; `fresh_agent_core`
  rejects empty `content`. Raise `max_tokens` (e.g. 16384) and the timeout
  (e.g. 900 s) in the explicit `AgentConfig`.

## Usage

```python
from fresh_agent_core import AgentConfig

config = AgentConfig(
    endpoint="https://opencode.ai/zen/go/v1",
    model="deepseek-v4.1-flash",
    api_key=os.environ["OPENCODE_GO_KEY"],
    headers={"x-opencode-session": os.environ["OPENCODE_SESSION_ID"]},
    timeout=900.0,
    max_tokens=16384,
)
result = ws3.agent.run("ws3_hint", HintInputs(goal="..."), config=config)
```

Credentials are never committed; read them from the environment or the local
OpenCode credential store at run time.
