#!/usr/bin/env python3

# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

"""
Neptune protocol code generator.

Reads npt_registry.json + overlay(s) and generates C headers for
command serialization and dispatch.

Usage:
    python3 npt_protocol.py --outdir <dir> --side host|guest \
        --json npt_registry.json --overlay npt_registry_overlay.json
"""

import argparse
import subprocess
import sys
from pathlib import Path

from mako.template import Template

from npt_registry import (
    TypeRegistry, NptType, Category,
    PRIMITIVE_NAMES, uuid_to_guid_init,
)
from npt_codegen import Gen


TOOLS_DIR = Path(__file__).resolve().parent
NPT_DIR = TOOLS_DIR.parent
TEMPLATE_DIR = NPT_DIR / 'templates'


# -----------------------------------------------------------------------
# File grouping
# -----------------------------------------------------------------------

def group_interfaces(interfaces):
    """
    Group interfaces by family (computed during registry resolution).
    Returns dict mapping family_name -> list of NptType, ordered by
    original interface order.
    """
    families = {}
    for iface in interfaces:
        if iface.name == 'IUnknown':
            continue
        families.setdefault(iface.family, []).append(iface)
    return families


# -----------------------------------------------------------------------
# Template rendering
# -----------------------------------------------------------------------

def render_template(name, **kwargs):
    # No module_directory: keep templates compiled in memory only.  Using a
    # shared on-disk cache causes the concurrent host + guest + client
    # custom_targets to race on the same .py / .pyc files and fail with
    # PermissionError on Windows.
    tmpl = Template(filename=str(TEMPLATE_DIR / name))
    return tmpl.render(**kwargs)


def write_file(outdir, filename, content):
    path = outdir / filename
    # Only write if content changed.  Meson tracks outputs by mtime, so
    # always touch the file even on a no-op write so the build system
    # considers the custom_target satisfied.
    #
    # Always write LF-only line endings.  MSVC's preprocessor (especially
    # with /utf-8) does not splice `\<CR><LF>` line continuations the way
    # `\<LF>` ones are spliced, so macro definitions with a trailing
    # backslash break apart if CRLF gets into the file (e.g. via Mako
    # rendering CRLF templates on Windows).
    if path.exists():
        existing = path.read_text(encoding='utf-8')
        if existing == content:
            path.touch()
            return
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f'  wrote {filename}')


# -----------------------------------------------------------------------
# Generators
# -----------------------------------------------------------------------

# Types with hand-written encode/decode in npt_cs_helpers.h
BUILTIN_STRUCT_NAMES = {'GUID', 'POINT', 'RECT', 'LONG'}

def _collect_struct_deps(ntype, out, seen, anon_names=None):
    """Recursively collect struct/union dependencies in order."""
    if ntype.name in seen:
        return
    if ntype.name in BUILTIN_STRUCT_NAMES:
        return  # hand-written in npt_cs_helpers.h
    seen.add(ntype.name)
    for field in ntype.fields:
        if field.type_ref and field.type_ref.category in (Category.STRUCT, Category.UNION):
            _collect_struct_deps(field.type_ref, out, seen, anon_names)
    # Skip appending anon types that are flattened into their parent's
    # emission — but their inner-field struct deps still need to be
    # walked above, otherwise a newly-added union arm pointing at
    # struct X won't pull X into the ordering before the parent.
    if not (anon_names and ntype.name in anon_names):
        out.append(ntype)


def collect_struct_types(registry):
    """
    Collect all struct and union types that need serialization,
    ordered so that dependencies come before dependents.
    Anonymous types that are used as unnamed fields are flattened inline.
    Anonymous types used as named fields need standalone encode/decode.
    """
    result = []
    seen = set()
    # Only exclude top-level anonymous types that are always accessed
    # through unnamed field flattening. Nested anonymous types that are
    # accessed via named fields (e.g. union members) need their functions.
    anon_names = set()
    for ntype in registry.anonymous_types:
        if not ntype.name:
            continue
        # Check if this anon type is only ever used as an unnamed field
        used_as_named = False
        for t in registry.types.values():
            for f in t.fields:
                if f.type_name == ntype.name and f.name is not None:
                    used_as_named = True
                    break
            if used_as_named:
                break
        if not used_as_named:
            anon_names.add(ntype.name)
    # Include anonymous types used as named fields FIRST
    for ntype in registry.anonymous_types:
        if ntype.name and ntype.name not in anon_names:
            _collect_struct_deps(ntype, result, seen, anon_names)

    for ntype in registry.structs + registry.unions:
        if ntype.name and ntype.name not in BUILTIN_STRUCT_NAMES:
            _collect_struct_deps(ntype, result, seen, anon_names)

    return result


def generate_cs(side, outdir):
    """Generate npt_protocol_{side}_cs.h and common cs/cs_helpers headers."""
    # Side-specific CS header
    tmpl_name = f'{side}_cs.h'
    content = render_template(tmpl_name)
    write_file(outdir, f'npt_protocol_{side}_cs.h', content)

    # Common files (idempotent -- both sides generate identical content)
    content = render_template('common_cs.h')
    write_file(outdir, 'npt_protocol_common_cs.h', content)

    content = render_template('cs_helpers.h')
    write_file(outdir, 'npt_protocol_common_cs_helpers.h', content)


def generate_defs(registry, outdir):
    """Generate npt_protocol_defs.h (shared definitions)."""
    interfaces = [i for i in registry.interfaces if i.uuid]
    gen = Gen(registry, is_host=True)

    content = render_template('defs.h',
        INTERFACES=interfaces,
        GEN=gen,
        uuid_to_guid_init=uuid_to_guid_init,
        WIRE_VERSION=registry.version,
    )
    write_file(outdir, 'npt_protocol_defs.h', content)


def generate_types(registry, outdir):
    """Generate common type alias and enum encode/decode."""
    # Topologically sort aliases so targets are defined before dependents.
    # E.g. UINT (-> uint32_t) must come before DXGI_USAGE (-> UINT).
    alias_types = []
    alias_set = set()

    def add_alias(ty):
        if ty.name in alias_set:
            return
        alias_set.add(ty.name)
        # If the target is itself an alias, add it first
        target = registry.get_type(ty.alias_target)
        if target and target.category == Category.ALIAS and target.name not in alias_set:
            add_alias(target)
        alias_types.append(ty)

    # Types with hand-written encode/decode in npt_cs_helpers.h or C keywords
    builtin_aliases = {'LONG', 'int', 'float', 'char', 'void'}

    for ty in registry.aliases:
        if ty.name and ty.alias_target:
            if ty.name in builtin_aliases:
                continue
            # Skip aliases to interface types (e.g. ID3DBlob -> ID3D10Blob)
            target = registry.get_type(ty.alias_target)
            if target and target.category == Category.INTERFACE:
                continue
            add_alias(ty)

    enum_types = [ty for ty in registry.enums if ty.name]

    struct_types = collect_struct_types(registry)
    content = render_template('types.h',
        ALIAS_TYPES=alias_types,
        ENUM_TYPES=enum_types,
        PRIMITIVE_NAMES=PRIMITIVE_NAMES,
        REG=registry,
        STRUCT_TYPES=struct_types,
    )
    write_file(outdir, 'npt_protocol_common_types.h', content)


def generate_structs(registry, gen, side, outdir):
    """Generate struct/union serialization."""
    struct_types = collect_struct_types(registry)

    content = render_template('structs.h',
        SIDE=side,
        IS_HOST=(side == 'host'),
        GEN=gen,
        STRUCT_TYPES=struct_types,
    )
    write_file(outdir, f'npt_protocol_{side}_structs.h', content)


def generate_commands(registry, gen, side, outdir):
    """Generate per-family command files."""
    families = group_interfaces(registry.interfaces)
    is_host = (side == 'host')
    is_guest = (side == 'guest')
    family_names = []

    for family_name, interfaces in sorted(families.items()):
        guard = family_name.upper()

        content = render_template('commands.h',
            SIDE=side,
            GUARD=guard,
            GROUP_NAME=family_name,
            INTERFACES=interfaces,
            FUNCTIONS=[],
            GEN=gen,
            IS_HOST=is_host,
            IS_GUEST=is_guest,
            FAMILY_STRUCTS=[],
        )
        write_file(outdir, f'npt_protocol_{side}_{family_name}.h', content)
        family_names.append(family_name)

    # Top-level functions
    if registry.functions:
        content = render_template('commands.h',
            SIDE=side,
            GUARD='TOPLEVEL',
            GROUP_NAME='toplevel',
            INTERFACES=[],
            FUNCTIONS=registry.functions,
            GEN=gen,
            IS_HOST=is_host,
            IS_GUEST=is_guest,
            FAMILY_STRUCTS=[],
        )
        write_file(outdir, f'npt_protocol_{side}_toplevel.h', content)
        family_names.append('toplevel')

    return family_names


def generate_client(registry, gen, outdir):
    """
    Generate per-family client-side COM headers and out-of-line .c files
    plus the global IID->ctor registration table.

    The "client" layer sits on top of the "guest" wire-encode/decode
    headers: it produces actual COM-shaped objects (vtable structs,
    default thunk bodies that call into the npt_call_/npt_async_
    encoders, AddRef/Release/QueryInterface defaults, IID-keyed
    constructor registration) that the consumer (mesa) can either use
    as-is or override slot-by-slot.

    For each interface family:
      npt_protocol_client_<family>.h  -- vtable struct + extern decls
      npt_protocol_client_<family>.c  -- thunk bodies + populator + ctor

    Plus one global file:
      npt_protocol_client_table.c  -- IID->ctor registration

    The .c bodies live OUT OF LINE so each TU that uses a family doesn't
    get its own copy of every thunk.
    """
    families = group_interfaces(registry.interfaces)
    family_names = []
    all_interfaces = []

    for family_name, interfaces in sorted(families.items()):
        # Skip families whose interfaces have no methods at all -- nothing
        # to generate.  (A few protocol entries are pure forward decls.)
        usable_ifaces = [i for i in interfaces if i.uuid]
        if not usable_ifaces:
            continue

        guard = family_name.upper()
        all_interfaces.extend(usable_ifaces)

        # Header
        content = render_template('client.h',
            GROUP_NAME=family_name,
            GUARD=guard,
            INTERFACES=usable_ifaces,
            GEN=gen,
        )
        write_file(outdir, f'npt_protocol_client_{family_name}.h', content)

        # Out-of-line implementation
        content = render_template('client.c',
            GROUP_NAME=family_name,
            GUARD=guard,
            INTERFACES=usable_ifaces,
            GEN=gen,
        )
        write_file(outdir, f'npt_protocol_client_{family_name}.c', content)

        family_names.append(family_name)

    # Global ctor table declaration -- consumed by the runtime
    # (npt_com.c) via #include, so the void npt_com_init_default_ctors()
    # forward decl doesn't need to live in the consumer any more.
    content = render_template('client_table.h')
    write_file(outdir, 'npt_protocol_client_table.h', content)

    # Global ctor table definition
    content = render_template('client_table.c',
        ALL_FAMILIES=family_names,
        ALL_INTERFACES=all_interfaces,
    )
    write_file(outdir, 'npt_protocol_client_table.c', content)

    # Family list (plain text, one family per line) -- mesa's meson.build
    # run_command()s `cat` on this file to populate npt_client_families
    # at configure time, keeping the list in sync with the registry
    # without needing to ship a Python dependency into the consumer.
    families_txt = '\n'.join(family_names) + '\n'
    write_file(outdir, 'npt_client_families.txt', families_txt)

    return family_names


def generate_dispatch(registry, gen, outdir, includes):
    """Generate dispatch headers (host-side only)."""
    all_interfaces = [i for i in registry.interfaces
                      if i.uuid and i.name != 'IUnknown' and i.methods]

    # Dispatch types (PFN typedefs, override structs, context)
    content = render_template('dispatch_types.h',
        GEN=gen,
        ALL_INTERFACES=all_interfaces,
        ALL_FUNCTIONS=registry.functions,
    )
    write_file(outdir, 'npt_protocol_host_dispatch_types.h', content)

    # Dispatch routing (method switches, UUID dispatch, entry point)
    content = render_template('dispatch.h',
        GEN=gen,
        ALL_INTERFACES=all_interfaces,
        ALL_FUNCTIONS=registry.functions,
        INCLUDES=includes,
    )
    write_file(outdir, 'npt_protocol_host_dispatch.h', content)


def _get_git_commit():
    """Get the current git commit hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return 'unknown'


def generate_umbrella(side, outdir, includes):
    """Generate umbrella header."""
    tmpl_name = f'{side}.h'
    content = render_template(tmpl_name, INCLUDES=includes,
                              GIT_COMMIT=_get_git_commit())
    write_file(outdir, f'npt_protocol_{side}.h', content)


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Neptune protocol code generator')
    parser.add_argument('--outdir', required=True, type=Path,
                        help='Output directory for generated headers')
    parser.add_argument('--side', required=True, choices=['host', 'guest'],
                        help='Generate host (decoder+dispatch) or guest (encoder) headers')
    parser.add_argument('--json', required=True, type=Path,
                        help='Path to npt_registry.json')
    parser.add_argument('--overlay', action='append', type=Path, default=[],
                        help='Path to overlay JSON (can be specified multiple times)')
    parser.add_argument('--interface-ids', type=Path,
                        default=NPT_DIR / 'npt_interface_ids.json',
                        help='Path to npt_interface_ids.json '
                             '(the GUID->interface-id pinning database)')
    parser.add_argument('--client-only', action='store_true',
                        help='Generate only the client-side COM headers + .c '
                             'files (vtables, default thunks, ctors, IID '
                             'table).  Useful when those outputs are owned '
                             'by a separate meson custom_target so the test '
                             'executables do not auto-compile the .c files.')

    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    # Load and resolve the type registry
    print(f'Loading {args.json}...')
    registry = TypeRegistry()
    registry.load(args.json, args.overlay,
                  interface_ids_path=args.interface_ids)
    registry.resolve()

    print(f'  {len(registry.interfaces)} interfaces, '
          f'{len(registry.functions)} functions, '
          f'{len(registry.structs)} structs, '
          f'{len(registry.enums)} enums, '
          f'{len(registry.unions)} unions')

    gen = Gen(registry, is_host=(args.side == 'host'))

    if args.client_only:
        if args.side != 'guest':
            print('ERROR: --client-only is only valid with --side guest',
                  file=sys.stderr)
            return 1
        print(f'Generating client-side COM headers in {args.outdir}...')
        generate_client(registry, gen, args.outdir)
        print('Done.')
        return 0

    print(f'Generating {args.side} headers in {args.outdir}...')

    # Always generate defs (shared)
    generate_defs(registry, args.outdir)

    # CS interface and helpers (generated, project provides npt_cs.h)
    generate_cs(args.side, args.outdir)

    # Types (common -- idempotent across sides)
    generate_types(registry, args.outdir)

    # All structs in the shared file
    generate_structs(registry, gen, args.side, args.outdir)

    # Commands (per-family + toplevel)
    includes = generate_commands(registry, gen, args.side, args.outdir)

    # Dispatch (host only)
    if args.side == 'host':
        generate_dispatch(registry, gen, args.outdir, includes)

    # Umbrella
    generate_umbrella(args.side, args.outdir, includes)

    print('Done.')
    if registry._warnings:
        print(f'\n{len(registry._warnings)} warning(s) emitted during generation.',
              file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())
