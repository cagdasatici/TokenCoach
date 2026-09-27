#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: live cost nudges from TokenCoach.

Installed into ~/.claude/settings.json from the menu bar app. Reads the hook
event on stdin, prints at most a short message for the user, never blocks.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tokencoach.nudge import main  # noqa: E402

if __name__ == "__main__":
    main()
