#!/usr/bin/env python3
#
# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0
#
# Allocate a new interface id in npt_interface_ids.json.
#
# The pinning file is the authoritative GUID <-> interface-id map.  It is
# keyed on the integer id (as a string because JSON only allows string
# keys), so the next free id is always max(int(k) for k in json) + 1.
# Retired entries keep their slot forever (protobuf field-number policy).
#
# Usage:
#   python3 tools/npt_allocate_interface_id.py IFoo aec22fb8-76f3-4639-9be0-28eb43a67a2e
#
# The script refuses to overwrite an existing GUID or name so repeated
# invocations with the same arguments are safe to re-run.

import argparse
import json
import re
import sys
from pathlib import Path

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def load(path):
    with open(path, 'r') as f:
        return json.load(f)


def save(path, data):
    # Stable formatting: sort by integer id, 2-space indent, trailing LF.
    ordered = dict(sorted(data.items(), key=lambda kv: int(kv[0])))
    with open(path, 'w') as f:
        json.dump(ordered, f, indent=2)
        f.write('\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('name', help='Interface name, e.g. ID3D11Buffer')
    p.add_argument('guid', help='UUID in canonical dashed form (lowercase)')
    p.add_argument(
        '--file',
        default=str(Path(__file__).resolve().parent.parent /
                    'npt_interface_ids.json'),
        help='Path to npt_interface_ids.json')
    args = p.parse_args()

    guid = args.guid.lower()
    if not UUID_RE.match(guid):
        sys.exit(f"error: {args.guid!r} is not a canonical dashed UUID")

    data = load(args.file)

    # Reject duplicates up front.
    for k, v in data.items():
        if v['guid'].lower() == guid:
            if v['name'] != args.name and not v.get('retired'):
                sys.exit(
                    f"error: guid {guid} already assigned to id {k} "
                    f"with a different name ({v['name']!r})")
            print(f"{args.name} already assigned id {k}")
            return
        if v['name'] == args.name and not v.get('retired'):
            sys.exit(
                f"error: name {args.name!r} already assigned to id {k} "
                f"with guid {v['guid']}")

    next_id = max(int(k) for k in data) + 1
    data[str(next_id)] = {'guid': guid, 'name': args.name}
    save(args.file, data)
    print(f"allocated id {next_id} -> {args.name}")


if __name__ == '__main__':
    main()
