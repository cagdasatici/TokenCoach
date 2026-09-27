#!/usr/bin/env python3
"""TokenCoach launcher: `python3 tokencoach.py [--help]`.

The code lives in the tokencoach/ package next to this file.
"""
import os
import sys

if sys.version_info < (3, 10):
    sys.exit(f"TokenCoach needs Python 3.10 or newer; this is {sys.version.split()[0]}. "
             "Install one with `brew install python`, or use the one-line installer.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tokencoach.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
