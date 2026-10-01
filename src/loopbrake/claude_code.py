"""The Claude Code adapter: hook events in, Brake calls through, Claude Code replies out.

Contracts: specs/004-claude-code-plugin/contracts/hooks.md and cli.md. It holds no stop logic of its
own (constitution Principle V): every decision is Brake.step().
"""
import hashlib
import os
import re
from pathlib import Path


def history_folder(cwd=None):
    """Where Claude Code keeps a working folder's history: every non-letter, non-digit becomes '-'."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    return root / re.sub(r"[^A-Za-z0-9]", "-", str(cwd or Path.cwd()))


def project_name(folder_name):
    """A LoopBrake project name for a history folder: readable, at most 50 characters, and unique."""
    return f"cc-{folder_name.lstrip('-')[-40:]}-{hashlib.sha256(folder_name.encode()).hexdigest()[:6]}"
