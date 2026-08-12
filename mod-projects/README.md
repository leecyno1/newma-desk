# Built-in Mod projects

Newma-Desk keeps its pinned built-in business and intelligence runtimes inside this directory
while preserving their independent repositories and runtimes:

- `vibe-research/` provides the default investment and research Mods.
- `vibe-trading/` provides the default quant and trading Mods.
- `world-intel-mcp/` provides the managed global intelligence data plane used by
  the Market global-situation map and the Event workspace.

The unified launcher discovers both directories automatically. Environment
variables are only needed when intentionally overriding these in-tree defaults.
The unified launcher creates `world-intel-mcp/.venv`, installs its dashboard
extra, and manages its local service on port `8501`.

Each child project retains its own `.git`, dependencies, backend, frontend, and
working tree. Do not flatten their history into the Newma-Desk repository.
