"""CLI entry point for Work4Me agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from work4me.config import Config, load_config
from work4me.core.orchestrator import Orchestrator


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
        "--hours", "-H", type=float, default=None, help="Time budget in hours (default: 4)"
    )
    start.add_argument(
        "--budget", "-b", type=int, default=None, help="Time budget in minutes (alternative to --hours)"
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
    start.add_argument(
        "--mode", type=str, choices=["sidebar", "manual"],
        default="sidebar", help="Operating mode (default: sidebar)"
    )
    start.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    start.add_argument(
        "--config", "-c", type=str, default=None,
        help="Path to TOML config file (default: ~/.config/work4me/config.toml)",
    )

    # stop
    sub.add_parser("stop", help="Gracefully stop the current session")

    # status
    sub.add_parser("status", help="Show current session status")

    # doctor
    sub.add_parser("doctor", help="Check system dependencies and permissions")

    return parser


def setup_logging(verbose: bool = False, log_level: str = "INFO") -> None:
    if verbose:
        level = logging.DEBUG
    else:
        level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


async def cmd_start(args: argparse.Namespace) -> int:
    config_path = Path(args.config) if getattr(args, "config", None) else None
    config = load_config(config_path)

    # Apply config log_level (reconfigure since basicConfig already called)
    setup_logging(verbose=getattr(args, "verbose", False), log_level=config.log_level)

    # CLI flags override TOML values
    working_dir = args.working_dir
    config.working_dir = str(Path(working_dir).resolve())
    config.mode = args.mode
    config.claude.model = args.model
    config.claude.max_budget_usd = args.max_budget

    # Resolve time budget: --budget (minutes) takes priority, then --hours, then default
    if args.budget is not None:
        time_budget_minutes = args.budget
    elif args.hours is not None:
        time_budget_minutes = int(args.hours * 60)
    else:
        time_budget_minutes = int(config.default_hours * 60)

    config.default_hours = time_budget_minutes / 60.0

    orchestrator = Orchestrator(config)
    try:
        await orchestrator.run(
            task_description=args.task,
            time_budget_minutes=time_budget_minutes,
            working_dir=config.working_dir,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    return 0


async def cmd_doctor(_args: argparse.Namespace) -> int:
    from work4me.doctor import DoctorChecks

    dc = DoctorChecks()
    results = dc.run_all()
    all_ok = True
    print("Checking system...\n")
    for r in results:
        if r.passed:
            print(f"  \u2713 {r.name} ({r.detail})")
        else:
            print(f"  \u2717 {r.name} — {r.detail}")
            all_ok = False
    print()
    if all_ok:
        print("All checks passed!")
    else:
        print("Some checks failed. See docs/11-distribution.md for setup.")
    return 0 if all_ok else 1


async def cmd_stop(_args: argparse.Namespace) -> int:
    config = Config()
    sock_path = config.runtime_dir / "daemon.sock"
    if not sock_path.exists():
        print("No active session to stop.")
        return 1

    try:
        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        writer.write(b"stop\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.readline(), timeout=5.0)
        print(response.decode().strip())
        writer.close()
        await writer.wait_closed()
    except (ConnectionRefusedError, FileNotFoundError):
        print("No active session to stop.")
        return 1
    except TimeoutError:
        print("Stop command sent but no response received.")
    return 0


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
        "stop": cmd_stop,
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
