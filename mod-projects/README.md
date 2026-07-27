# Built-in Mod projects

Newma-Dock keeps the two first-party business applications inside this directory
while preserving their independent repositories and runtimes:

- `vibe-research/` provides the default investment and research Mods.
- `vibe-trading/` provides the default quant and trading Mods.

The unified launcher discovers both directories automatically. Environment
variables are only needed when intentionally overriding these in-tree defaults.

Each child project retains its own `.git`, dependencies, backend, frontend, and
working tree. Do not flatten their history into the Newma-Dock repository.
