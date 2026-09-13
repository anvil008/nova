#!/usr/bin/env python3
"""Native PreToolUse adapter for Nova's implementer write routing."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from write_routing import hook_main

if __name__ == '__main__':
    hook_main()
