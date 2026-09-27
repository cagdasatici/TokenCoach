#!/usr/bin/env python3
"""TokenCoach launcher: `python3 tokencoach.py [--help]`.

The code lives in the tokencoach/ package next to this file.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tokencoach.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
