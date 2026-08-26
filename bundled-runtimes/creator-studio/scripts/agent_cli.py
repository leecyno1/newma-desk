#!/usr/bin/env python3
"""统一本地 CLI Agent 调用工具。

使用方式:
    python scripts/agent_cli.py --prompt "你的问题"
    python scripts/agent_cli.py --prompt-file prompt.txt --output out.txt
    python scripts/agent_cli.py --agent qoder-cli --prompt "..."

默认按优先级尝试: qoder-cli → claude → codex → gemini → qwen
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

CLI_PRIORITY = ["qoder-cli", "claude", "codex", "gemini", "qwen"]

CLI_DEFINITIONS = {
    "qoder-cli": {
        "binary": "qodercli",
        "args": ["-p"],
        "prompt_via_stdin": False,
        "prompt_as_last_arg": True,
        "clean_env": True,
    },
    "claude": {
        "binary": "claude",
        "args": ["--print"],
        "prompt_via_stdin": True,
    },
    "codex": {
        "binary": "codex",
        "args": ["exec", "--skip-git-repo-check"],
        "prompt_via_stdin": True,
    },
    "gemini": {
        "binary": "gemini",
        "args": [],
        "prompt_via_stdin": True,
    },
    "qwen": {
        "binary": "qwen",
        "args": [],
        "prompt_via_stdin": True,
    },
}


def clean_agent_env() -> dict[str, str]:
    """Strip ALL QODER_* / QODERCN_* env vars so qoder-cli runs in normal auth mode."""
    env = os.environ.copy()
    for k in list(env.keys()):
        if k.startswith("QODER_") or k.startswith("QODERCN_") or k.startswith("QODERWORK_"):
            env.pop(k, None)
    return env


def invoke_cli(prompt: str, agent: str | None = None, timeout: int = 300, cwd: str | None = None) -> tuple[str, str, int]:
    """调用本地 CLI agent，返回 (agent_used, stdout, exit_code)。"""
    agents = [agent] if agent else CLI_PRIORITY
    last_err = ""
    for agent_id in agents:
        d = CLI_DEFINITIONS.get(agent_id)
        if not d:
            continue
        binary = shutil.which(d["binary"])
        if not binary:
            continue

        args = [binary, *d["args"]]
        input_text = prompt if d.get("prompt_via_stdin") else None
        if d.get("prompt_as_last_arg"):
            args.append(prompt)

        env = clean_agent_env() if d.get("clean_env") else None
        try:
            result = subprocess.run(
                args,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"[agent_cli] used {agent_id} ({binary})", file=sys.stderr)
                return agent_id, result.stdout, 0
            last_err = f"{agent_id} exit={result.returncode} stderr={result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            last_err = f"{agent_id} timeout after {timeout}s"
        except OSError as e:
            last_err = f"{agent_id} os error {e}"

    raise RuntimeError(f"no CLI agent available: {last_err}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="prompt text (or use --prompt-file)")
    parser.add_argument("--prompt-file", help="read prompt from file")
    parser.add_argument("--agent", help=f"force agent ({', '.join(CLI_PRIORITY)})")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", help="write stdout to file")
    parser.add_argument("--cwd", help="working directory")
    args = parser.parse_args()

    if args.prompt_file:
        prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = sys.stdin.read()
    if not prompt.strip():
        print("error: empty prompt", file=sys.stderr)
        return 2

    agent, out, code = invoke_cli(prompt, args.agent, args.timeout, args.cwd)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"[agent_cli] output saved to {args.output} (agent={agent}, bytes={len(out)})", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0 if code == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
