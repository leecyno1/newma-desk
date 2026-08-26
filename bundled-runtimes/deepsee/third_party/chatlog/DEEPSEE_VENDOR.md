# Vendored Chatlog dependency

This directory contains the buildable Chatlog source used by Deepsee's local
WeChat history sidecar.

- Upstream fork: `https://github.com/teest114514/chatlog_alpha`
- Imported commit: `bfb031f7f94923a97ac186f5f048ef6006ab3d63`
- Imported from the maintained local working tree on 2026-08-04, including the
  macOS detector and Deepsee compatibility fixes that had not yet been committed
  upstream.
- License and usage restrictions: see `LICENSE` and `DISCLAIMER.md` in this
  directory. These files are preserved unchanged from the dependency source.

Deepsee does not modify the Go module path. Build it with:

```bash
bash scripts/build_chatlog.sh
```

The generated executable is written to `.local/chatlog/bin/` and is intentionally
not committed.
