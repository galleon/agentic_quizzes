from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

SYSTEM_PROMPT = """You are a careful local automation agent.

You must respond with JSON only.

Allowed response formats:

1) Think:
{"action":"think","message":"brief reasoning"}

2) Run one command:
{"action":"command","command":["python","tool.py","arg1","arg2"],"why":"brief reason"}

3) Finish:
{"action":"final","summary":"what was achieved"}

Rules:
- Never output anything except valid JSON.
- Use only one command at a time.
- Prefer inspection commands first.
- Never assume a file exists: inspect first.
- If a command fails, adapt.
- Keep commands short.
- Do not use shell syntax, pipes, redirection, &&, ||, ;, or wildcards.
- Command must be a JSON array of strings.
- Stay inside the workspace.
"""

USER_TEMPLATE = """Objective:
{objective}

Workspace:
{workspace}

Files visible at start:
{initial_tree}

Recent execution history:
{history}

Decide the next best action.
"""

ALLOWED_COMMANDS = {
    "python",
    "python3",
    "ls",
    "find",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "rg",
    "pwd",
    "echo",
    "mkdir",
    "cp",
    "mv",
}

FORBIDDEN_TOKENS = {";", "&&", "||", "|", ">", ">>", "<", "$(", "`"}

@dataclass
class StepResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

class SandboxError(Exception):
    pass

class BashSandbox:
    def __init__(self, workspace: Path, timeout_seconds: int = 20, max_output_chars: int = 12000) -> None:
        self.workspace = workspace.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, command: list[str]) -> StepResult:
        self._validate_command(command)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.workspace),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        proc = subprocess.run(
            command,
            cwd=str(self.workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            shell=False,
        )
        return StepResult(
            command=command,
            returncode=proc.returncode,
            stdout=self._truncate(proc.stdout),
            stderr=self._truncate(proc.stderr),
        )

    def _validate_command(self, command: list[str]) -> None:
        if not command:
            raise SandboxError("Empty command.")
        prog = command[0]
        if prog not in ALLOWED_COMMANDS:
            raise SandboxError(f"Command not allowed: {prog}")
        for token in command:
            if not isinstance(token, str):
                raise SandboxError("All command tokens must be strings.")
            for bad in FORBIDDEN_TOKENS:
                if bad in token:
                    raise SandboxError(f"Forbidden shell token detected: {bad}")
        for token in command[1:]:
            if token.startswith("/"):
                resolved = Path(token).resolve()
                if not self._is_within_workspace(resolved):
                    raise SandboxError(f"Absolute path outside workspace: {token}")
            if "/" in token or token.startswith("."):
                candidate = (self.workspace / token).resolve()
                if not self._is_within_workspace(candidate):
                    raise SandboxError(f"Path escapes workspace: {token}")

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace)
            return True
        except ValueError:
            return False

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        return text[: self.max_output_chars] + "\n...[truncated]..."

class MiniAgent:
    def __init__(self, model: str, base_url: str, api_key: str, workspace: Path, max_turns: int = 20) -> None:
        self.client = OpenAI(base_url=base_url.rstrip("/") + "/v1", api_key=api_key)
        self.model = model
        self.workspace = workspace.resolve()
        self.max_turns = max_turns
        self.sandbox = BashSandbox(self.workspace)
        self.history: list[dict[str, Any]] = []

    def run(self, objective: str) -> str:
        initial_tree = self._list_workspace()
        for _ in range(self.max_turns):
            prompt = USER_TEMPLATE.format(
                objective=objective,
                workspace=str(self.workspace),
                initial_tree=initial_tree,
                history=json.dumps(self.history[-8:], ensure_ascii=False, indent=2),
            )
            action = self._ask_model(prompt)
            kind = action.get("action")

            if kind == "think":
                self.history.append({"type": "think", "message": action.get("message", "")})
                continue

            if kind == "command":
                raw_cmd = action.get("command")
                if not isinstance(raw_cmd, list) or not all(isinstance(x, str) for x in raw_cmd):
                    self.history.append({"type": "sandbox_error", "error": "Model returned invalid command format."})
                    continue
                try:
                    result = self.sandbox.run(raw_cmd)
                    self.history.append(
                        {
                            "type": "command",
                            "why": action.get("why", ""),
                            "command": raw_cmd,
                            "returncode": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        }
                    )
                    print(f"\n$ {' '.join(shlex.quote(x) for x in raw_cmd)}")
                    if result.stdout.strip():
                        print(result.stdout)
                    if result.stderr.strip():
                        print("[stderr]")
                        print(result.stderr)
                except Exception as exc:
                    self.history.append({"type": "sandbox_error", "command": raw_cmd, "error": str(exc)})
                continue

            if kind == "final":
                return action.get("summary", "")

            self.history.append({"type": "protocol_error", "raw": action})
        return "Stopped after reaching max_turns without final answer."

    def _ask_model(self, user_prompt: str) -> dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            max_tokens=600,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content or ""
        return self._extract_json(content)

    def _extract_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if fenced:
            data = json.loads(fenced.group(1).strip())
            if isinstance(data, dict):
                return data
        obj = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if obj:
            data = json.loads(obj.group(1))
            if isinstance(data, dict):
                return data
        raise ValueError("Model did not return valid JSON.")

    def _list_workspace(self) -> str:
        lines = []
        for path in sorted(self.workspace.rglob("*")):
            rel = path.relative_to(self.workspace)
            if rel.parts and rel.parts[0].startswith("."):
                continue
            lines.append(str(rel) + ("/" if path.is_dir() else ""))
            if len(lines) >= 200:
                lines.append("...[truncated]...")
                break
        return "\n".join(lines) if lines else "(empty workspace)"

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Minimal guarded bash agent for vLLM-served models")
    parser.add_argument("objective")
    parser.add_argument("--workspace", default="./workspace")
    parser.add_argument("--model", default="qwen3.5")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="local-token")
    parser.add_argument("--max-turns", type=int, default=20)
    args = parser.parse_args()

    agent = MiniAgent(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        workspace=Path(args.workspace),
        max_turns=args.max_turns,
    )
    print(agent.run(args.objective))
