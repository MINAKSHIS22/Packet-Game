"""Packet Panic - entry point.

Run:  python main.py            (fixed demo seed 42, reproducible)
      python main.py --seed 7   (another reproducible run)
      python main.py --random   (different random events every run)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pygame  # noqa: F401
except ImportError:
    print("Pygame is not installed. Run:  pip install -r requirements.txt")
    sys.exit(1)

from game.game import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Packet Panic - The Network Survival Game")
    parser.add_argument("--seed", type=int, default=42, help="random seed for reproducible demos")
    parser.add_argument("--random", action="store_true", help="use a different random seed every mission")
    args = parser.parse_args()
    main(seed=None if args.random else args.seed)
