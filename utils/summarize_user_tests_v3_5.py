"""CLI for aggregating AOMatch v3.5 real-user-test logs."""

import argparse
import json
from pathlib import Path

from utils.user_test_v3_5 import write_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/user_tests"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(write_summary(args.data_dir, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
