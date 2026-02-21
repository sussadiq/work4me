"""CLI entry point for Work4Me agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from work4me.config import Config


logger = logging.getLogger("work4me")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="work4me",
        description="Desktop AI agent for autonomous software engineering",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    start = sub.add_parser("start", help="Start a work session")
    start.add_argument("--task", "-t", required=True, help="Task description")
    start.add_argument(
        "--hours", "-H", type=float, default=4.0, help="Time budget in hours (default: 4)"
    )
    start.add_argument(
        "--working-dir", "-d", type=str, default=".", help="Project directory"
    )
    start.add_argument(
        "--model", "-m", type=str, default="sonnet", help="Claude model (default: sonnet)"
    )
    start.add_argument(
        "--max-budget", type=float, default=5.0, help="Max Claude API cost in USD"
    )
    start.add_argument("--verbose", "-v", action="store_true", help="Debug logging")

    # stop
    sub.add_parser("stop", help="Gracefully stop the current session")

    # status
    sub.add_parser("status", help="Show current session status")

    # doctor
    sub.add_parser("doctor", help="Check system dependencies and permissions")

    return parser


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def cmd_start(args: argparse.Namespace) -> int:
    config = Config(
        working_dir=str(Path(args.working_dir).resolve()),
        default_hours=args.hours,
    )
    config.claude.model = args.model
    config.claude.max_budget_usd = args.max_budget

    from work4me.core.orchestrator import Orchestrator

    orchestrator = Orchestrator(config)
    try:
        await orchestrator.run(
            task_description=args.task,
            time_budget_minutes=int(args.hours * 60),
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    return 0


async def cmd_doctor(_args: argparse.Namespace) -> int:
    import shutil

    checks = [
        ("python3", "Python 3.11+"),
        ("node", "Node.js 18+"),
        ("claude", "Claude Code CLI"),
        ("tmux", "tmux"),
        ("nvim", "Neovim"),
        ("ydotool", "ydotool"),
        ("wl-copy", "wl-clipboard"),
    ]

    all_ok = True
    print("Checking dependencies...\n")
    for cmd, label in checks:
        found = shutil.which(cmd)
        if found:
            print(f"  \u2713 {label} ({found})")
        else:
            print(f"  \u2717 {label} — NOT FOUND")
            all_ok = False

    # Check uinput access
    print("\nChecking permissions...\n")
    uinput = Path("/dev/uinput")
    if uinput.exists() and uinput.stat().st_mode & 0o060:
        print("  \u2713 /dev/uinput accessible")
    else:
        print("  \u2717 /dev/uinput — not accessible (run install.sh)")
        all_ok = False

    # Check Wayland
    wayland = "WAYLAND_DISPLAY" in __import__("os").environ
    if wayland:
        print("  \u2713 Wayland session detected")
    else:
        print("  \u2717 Wayland session not detected")

    print()
    if all_ok:
        print("All checks passed!")
    else:
        print("Some checks failed. See docs/11-distribution.md for setup instructions.")
    return 0 if all_ok else 1


async def cmd_status(_args: argparse.Namespace) -> int:
    config = Config()
    state_file = config.runtime_dir / "state.json"
    if state_file.exists():
        import json
        state = json.loads(state_file.read_text())
        print(f"State: {state.get('state', 'UNKNOWN')}")
        print(f"Task: {state.get('task_description', 'N/A')}")
        print(f"Elapsed: {state.get('elapsed_minutes', 0):.0f} min")
        print(f"Budget: {state.get('time_budget_minutes', 0):.0f} min")
    else:
        print("No active session.")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(getattr(args, "verbose", False))

    commands = {
        "start": cmd_start,
        "stop": lambda a: asyncio.coroutine(lambda: 0)(),
        "status": cmd_status,
        "doctor": cmd_doctor,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    rc = asyncio.run(handler(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
