#!/usr/bin/env python3
"""Pre-rename entry point, kept so older installs keep starting.

Installs made before the app was renamed TokenCoach launch this file. It runs
TokenCoach, which then moves the install to ~/.tokencoach by itself (see
tokencoach/legacy.py). New installs use tokencoach.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tokencoach.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
