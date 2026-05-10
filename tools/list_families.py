#!/usr/bin/env python3

# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

"""Print sorted interface family names from the Neptune protocol registry.

Used by meson.build at configure time to derive the per-family output
file list instead of hard-coding it.
"""

import argparse
from pathlib import Path

from npt_registry import TypeRegistry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', required=True, type=Path,
                        help='Path to npt_registry.json')
    parser.add_argument('--overlay', action='append', type=Path, default=[],
                        help='Path to overlay JSON')
    args = parser.parse_args()

    registry = TypeRegistry()
    registry.load(args.json, args.overlay)
    registry.resolve()

    families = set()
    for iface in registry.interfaces:
        if iface.name != 'IUnknown':
            families.add(iface.family)
    for name in sorted(families):
        print(name)


if __name__ == '__main__':
    main()
