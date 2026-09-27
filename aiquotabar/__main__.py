"""AIQuotaBar entry point."""

import sys

USAGE = """usage: claude_bar.py [option]
  (none)                 run the menu bar app
  --history, -H          print quota history
  --ledger               index local Claude Code / Cowork / Codex logs, print today's spend
  --dashboard            index, then write and open the usage dashboard (alias: --report)
  --optimize             index, then ask Claude for usage advice (uses your quota)
  --import-export PATH   import a claude.ai or ChatGPT data export (estimated tokens)
"""


def _ledger_cli(cmd: str, args: list[str]):
    from aiquotabar import ledger
    from aiquotabar.config import load_config
    config = load_config()
    conn = ledger.open_ledger()
    counts = ledger.ingest(conn, overrides=ledger.ledger_overrides(config))
    print(f"Indexed {counts['files']} changed files: +{counts['prompts']} prompts, "
          f"+{counts['calls']} responses")
    if cmd == "--ledger":
        s = ledger.today_summary(conn)
        print(f"Today: {ledger.fmt_usd(s['cost'])} API-equivalent, {s['prompts']} prompts, "
              f"{ledger.fmt_tokens(s['tokens'])} tokens")
        if s["top_project"]:
            print(f"Top project: {s['top_project']['project']} "
                  f"{ledger.fmt_usd(s['top_project']['cost'])}")
        if s["top_prompt"]:
            text = " ".join(s["top_prompt"]["text"].split())[:80]
            print(f"Top prompt: {text!r} {ledger.fmt_usd(s['top_prompt']['cost'])}")
    elif cmd in ("--dashboard", "--report"):
        from aiquotabar.ledger_report import write_report, open_file
        path = write_report(conn, config)
        print(path)
        open_file(path)
    elif cmd == "--optimize":
        from aiquotabar.optimizer import run_optimizer
        from aiquotabar.ledger_report import open_file
        print("Asking Claude for usage advice (takes a minute or two)...")
        path = run_optimizer(conn)
        print(path)
        open_file(path)
    elif cmd == "--import-export":
        if not args:
            sys.exit(USAGE)
        from aiquotabar.chat_import import import_export
        res = import_export(conn, args[0])
        print(f"Imported {res['prompts']} prompts and {res['replies']} replies from "
              f"{res['conversations']} {res['source']} conversations (estimated tokens)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd in ("--history", "-H"):
        from aiquotabar.history import cli_history
        cli_history()
    elif cmd in ("--ledger", "--dashboard", "--report", "--optimize", "--import-export"):
        _ledger_cli(cmd, sys.argv[2:])
    elif cmd in ("--help", "-h"):
        print(USAGE)
    else:
        from aiquotabar.ui import ClaudeBar
        ClaudeBar().run()


if __name__ == "__main__":
    main()
