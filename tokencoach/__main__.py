"""TokenCoach entry point."""

import sys

USAGE = """usage: tokencoach.py [option]
  (none)                 run the menu bar app
  --history, -H          print quota history
  --ledger               index local Claude Code / Cowork / Codex logs, print today's spend
  --dashboard            index, then write and open the usage dashboard (alias: --report)
  --optimize             index, then ask Claude for usage advice (uses your quota)
  --import-export PATH   import a claude.ai or ChatGPT data export (estimated tokens)
  --demo                 open the dashboard with sample data (reads and changes nothing of yours)
  --screenshots DIR      write the README screenshots from sample data (needs Google Chrome)
"""


def _demo(serve: bool = True, shots_dir: str | None = None):
    """Sample data in its own folder, so none of the person's data is involved."""
    import os
    import tempfile
    data_dir = os.path.join(tempfile.gettempdir(), "tokencoach-demo")
    if "tokencoach.config" in sys.modules:
        # Paths and the demo flag are fixed when the config is first imported;
        # if that already happened with real settings, the sandbox can't hold.
        sys.exit("--demo must start in a fresh process (run: tokencoach --demo)")
    os.environ["TOKENCOACH_DATA_DIR"] = data_dir
    os.environ["TOKENCOACH_DEMO"] = "1"
    from tokencoach import demo, ledger
    from tokencoach.config import load_config
    demo.prepare(data_dir)
    if shots_dir:
        from tokencoach.screenshots import capture
        for path in capture(ledger.open_ledger(), load_config(), shots_dir):
            print(path)
        return
    from tokencoach.server import DashboardServer
    from tokencoach.ledger_report import open_file
    import secrets
    import time
    srv = DashboardServer(secrets.token_urlsafe(16), app=None, port=0).start()
    print(f"TokenCoach demo (sample data) at {srv.url}\nPress Ctrl-C to stop.")
    open_file(srv.url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.stop()


def _ledger_cli(cmd: str, args: list[str]):
    from tokencoach import ledger
    from tokencoach.config import load_config
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
        from tokencoach.ledger_report import write_report, open_file
        path = write_report(conn, config)
        print(path)
        open_file(path)
    elif cmd == "--optimize":
        from tokencoach.optimizer import run_optimizer
        from tokencoach.ledger_report import open_file
        print("Asking Claude for usage advice (takes a minute or two)...")
        path = run_optimizer(conn)
        print(path)
        open_file(path)
    elif cmd == "--import-export":
        if not args:
            sys.exit(USAGE)
        from tokencoach.chat_import import import_export
        res = import_export(conn, args[0])
        print(f"Imported {res['prompts']} prompts and {res['replies']} replies from "
              f"{res['conversations']} {res['source']} conversations (estimated tokens)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd in ("--history", "-H"):
        from tokencoach.history import cli_history
        cli_history()
    elif cmd in ("--ledger", "--dashboard", "--report", "--optimize", "--import-export"):
        _ledger_cli(cmd, sys.argv[2:])
    elif cmd == "--demo":
        _demo()
    elif cmd == "--screenshots":
        _demo(shots_dir=sys.argv[2] if len(sys.argv) > 2 else "assets")
    elif cmd in ("--help", "-h"):
        print(USAGE)
    else:
        from tokencoach.ui import TokenCoachApp
        TokenCoachApp().run()


if __name__ == "__main__":
    main()
