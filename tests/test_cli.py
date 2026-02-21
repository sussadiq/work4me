# tests/test_cli.py
from work4me.cli import build_parser


def test_start_accepts_mode_flag():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--mode", "ai-assisted"])
    assert args.mode == "ai-assisted"


def test_start_default_mode_is_manual():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4"])
    assert args.mode == "manual"


def test_start_accepts_working_dir():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--dir", "/tmp/project"])
    assert args.dir == "/tmp/project"
