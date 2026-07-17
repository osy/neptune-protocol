#!/usr/bin/env python3

# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

"""
Generate a Microsoft DirectX-compatible C header from npt_registry.json.

The output header (npt_protocol_directx.h) contains all type definitions
(enums, structs, unions, constants, typedefs, interface forward declarations,
and top-level function declarations) in a layout-compatible format with
Microsoft's DirectX SDK headers.

Usage:
    python3 gen_headers.py --json npt_registry.json \
        --overlay npt_registry_overlay.json \
        --output npt_protocol_directx.h
"""

import argparse
import os
import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from npt_registry import TypeRegistry, Category, NptType, NptField, PRIMITIVE_NAMES


# -----------------------------------------------------------------------
# Dependency-ordered struct/union collection (same logic as npt_protocol.py)
# -----------------------------------------------------------------------

def _collect_struct_deps(ntype, out, seen):
    """Recursively collect struct/union dependencies in order."""
    if ntype.name in seen:
        return
    seen.add(ntype.name)
    for field in ntype.fields:
        if field.type_ref and field.type_ref.category in (Category.STRUCT, Category.UNION):
            _collect_struct_deps(field.type_ref, out, seen)
    out.append(ntype)


def collect_struct_types(registry):
    """Collect all struct and union types, dependencies before dependents."""
    result = []
    seen = set()
    for ntype in registry.anonymous_types:
        if ntype.name:
            _collect_struct_deps(ntype, result, seen)
    for ntype in registry.structs + registry.unions:
        if ntype.name:
            _collect_struct_deps(ntype, result, seen)
    return result


# -----------------------------------------------------------------------
# Windows base types
# -----------------------------------------------------------------------

# Windows base types to emit in the #ifndef _WIN32 block.
# Order matters for dependencies.
WINDOWS_BASE_TYPES = [
    ('VOID', 'typedef void VOID;'),
    ('HRESULT', 'typedef int32_t HRESULT;'),
    ('LONG', 'typedef int32_t LONG;'),
    ('INT', 'typedef int32_t INT;'),
    ('BOOL', 'typedef int32_t BOOL;'),
    ('SHORT', 'typedef int16_t SHORT;'),
    ('UINT', 'typedef uint32_t UINT;'),
    ('ULONG', 'typedef uint32_t ULONG;'),
    ('DWORD', 'typedef uint32_t DWORD;'),
    ('USHORT', 'typedef uint16_t USHORT;'),
    ('BYTE', 'typedef uint8_t BYTE;'),
    ('UCHAR', 'typedef uint8_t UCHAR;'),
    ('CHAR', 'typedef int8_t CHAR;'),
    ('WCHAR', 'typedef uint16_t WCHAR;'),
    ('UINT8', 'typedef uint8_t UINT8;'),
    ('UINT16', 'typedef uint16_t UINT16;'),
    ('UINT32', 'typedef uint32_t UINT32;'),
    ('UINT64', 'typedef uint64_t UINT64;'),
    ('INT8', 'typedef int8_t INT8;'),
    ('INT16', 'typedef int16_t INT16;'),
    ('INT32', 'typedef int32_t INT32;'),
    ('INT64', 'typedef int64_t INT64;'),
    ('LONGLONG', 'typedef int64_t LONGLONG;'),
    ('ULONGLONG', 'typedef uint64_t ULONGLONG;'),
    ('LARGE_INTEGER', 'typedef int64_t LARGE_INTEGER;'),
    ('SIZE_T', 'typedef uint64_t SIZE_T;'),
    ('LONG_PTR', 'typedef int64_t LONG_PTR;'),
    ('FLOAT', 'typedef float FLOAT;'),
    ('DOUBLE', 'typedef double DOUBLE;'),
    ('HANDLE', 'typedef uint64_t HANDLE;'),
    ('HWND', 'typedef uint64_t HWND;'),
    ('HMODULE', 'typedef uint64_t HMODULE;'),
    ('HMONITOR', 'typedef uint64_t HMONITOR;'),
]

# Set of names emitted in the Windows base types block
WINDOWS_BASE_NAMES = {name for name, _ in WINDOWS_BASE_TYPES}
# Also add types defined as structs in the preamble
PREAMBLE_STRUCT_NAMES = {'GUID', 'IID', 'CLSID', 'POINT', 'RECT',
                         'SECURITY_ATTRIBUTES'}
PREAMBLE_NAMES = WINDOWS_BASE_NAMES | PREAMBLE_STRUCT_NAMES | {
    'REFGUID', 'REFIID', 'REFCLSID',
}

# Type names that are provided by Win32 <windows.h> on MinGW.  These must
# not be re-typedef'd in the protocol header on MinGW because they conflict
# with windows.h.  On native Linux they're emitted normally as part of the
# fallback section.
WIN32_BASE_NAMES = WINDOWS_BASE_NAMES | PREAMBLE_STRUCT_NAMES | {
    'REFGUID', 'REFIID', 'REFCLSID',
    'LUID', 'SIZE', 'HDC',
}


# -----------------------------------------------------------------------
# Header writer
# -----------------------------------------------------------------------

class HeaderWriter:
    def __init__(self, registry):
        self.reg = registry
        self.out = StringIO()
        self._undefined_types = set()  # types referenced but not in registry

    def write(self, text=''):
        self.out.write(text)

    def writeln(self, text=''):
        self.out.write(text + '\n')

    def result(self):
        return self.out.getvalue()

    # -------------------------------------------------------------------
    # Collect undefined referenced types
    # -------------------------------------------------------------------

    def _collect_undefined_types(self):
        """Find types used in struct/union fields or function params that
        are not defined in the registry or the preamble."""
        known = set(self.reg.types.keys()) | PREAMBLE_NAMES | PRIMITIVE_NAMES | {
            'void', 'char', 'wchar_t', 'int', 'unsigned', 'long', 'short',
        }
        undefined = set()

        def check_field(field):
            if not field.type_name:
                return
            if field.type_name not in known:
                undefined.add(field.type_name)

        for ntype in self.reg.types.values():
            for f in ntype.fields:
                check_field(f)
            for p in ntype.params:
                check_field(p)
            for m in ntype.methods:
                for p in m.params:
                    check_field(p)

        self._undefined_types = undefined

    # -------------------------------------------------------------------
    # Top-level sections
    # -------------------------------------------------------------------

    def emit_preamble(self):
        self.writeln('/*')
        self.writeln(' * Auto-generated by gen_headers.py -- do not edit.')
        self.writeln(' *')
        self.writeln(' * Microsoft DirectX-compatible type definitions derived from')
        self.writeln(' * npt_registry.json.  Layout-compatible with the Windows SDK headers.')
        self.writeln(' */')
        self.writeln()
        self.writeln('#ifndef NPT_PROTOCOL_DIRECTX_H')
        self.writeln('#define NPT_PROTOCOL_DIRECTX_H')
        self.writeln()
        # Calling convention macros for COM ABI compatibility.  Defined here
        # so the generated guest proxy headers (which declare COM-style
        # function pointers using NPT_STDMETHODCALLTYPE) compile without
        # depending on any consumer header.  Guarded so consumers that
        # define their own copies don't get redefinition errors.
        self.writeln('#ifndef NPT_STDMETHODCALLTYPE')
        self.writeln('#  if defined(_WIN32)')
        self.writeln('#    define NPT_STDMETHODCALLTYPE __stdcall')
        self.writeln('#  elif defined(__APPLE__) && defined(__x86_64__)')
        self.writeln('#    define NPT_STDMETHODCALLTYPE __attribute__((ms_abi))')
        self.writeln('#  else')
        self.writeln('#    define NPT_STDMETHODCALLTYPE')
        self.writeln('#  endif')
        self.writeln('#endif')
        self.writeln()

    def emit_footer(self):
        self.writeln('#endif /* NPT_PROTOCOL_DIRECTX_H */')

    def emit_windows_types(self):
        # Windows MSVC: pull in the full SDK headers (Windows 10/11).
        # Windows MinGW: pull in <windows.h> for the base types but skip the
        #   D3D headers (which are too old).  The protocol's own fallback
        #   typedefs cover the missing D3D types.
        # Native Linux: use protocol fallbacks for everything.
        self.writeln('#if defined(_WIN32) && !defined(__MINGW32__)')
        self.writeln()
        for idl in self.reg.source_files:
            header = idl.replace('.idl', '.h')
            self.writeln(f'#include <{header}>')
        self.writeln()
        self.writeln('#elif defined(__MINGW32__)')
        self.writeln()
        self.writeln('/* Pull in basic Win32 types (HRESULT, GUID, LONG, ...) from windows.h')
        self.writeln(' * but rely on this protocol header for the D3D-specific types that')
        self.writeln(' * MinGW\'s d3d11.h / d3d12.h are missing.  unknwn.h provides IUnknown. */')
        self.writeln('#ifndef WIN32_LEAN_AND_MEAN')
        self.writeln('#  define WIN32_LEAN_AND_MEAN')
        self.writeln('#endif')
        self.writeln('#include <windows.h>')
        self.writeln('#include <unknwn.h>')
        self.writeln('#include <stdint.h>')
        self.writeln()
        self.writeln('#else /* !_WIN32 (native Linux) */')
        self.writeln()
        self.writeln('#include <stdint.h>')
        self.writeln('#include <stddef.h>')
        self.writeln()
        for _name, defn in WINDOWS_BASE_TYPES:
            self.writeln(defn)
        self.writeln()
        # GUID struct
        self.writeln('typedef struct _GUID {')
        self.writeln('    uint32_t Data1;')
        self.writeln('    uint16_t Data2;')
        self.writeln('    uint16_t Data3;')
        self.writeln('    uint8_t Data4[8];')
        self.writeln('} GUID;')
        self.writeln()
        self.writeln('typedef GUID IID;')
        self.writeln('typedef GUID CLSID;')
        self.writeln('typedef const GUID *REFGUID;')
        self.writeln('typedef const GUID *REFIID;')
        self.writeln('typedef const GUID *REFCLSID;')
        self.writeln()
        # POINT
        self.writeln('typedef struct tagPOINT {')
        self.writeln('    LONG x;')
        self.writeln('    LONG y;')
        self.writeln('} POINT;')
        self.writeln()
        # RECT
        self.writeln('typedef struct tagRECT {')
        self.writeln('    LONG left;')
        self.writeln('    LONG top;')
        self.writeln('    LONG right;')
        self.writeln('    LONG bottom;')
        self.writeln('} RECT;')
        self.writeln()
        # SECURITY_ATTRIBUTES
        self.writeln('typedef struct _SECURITY_ATTRIBUTES {')
        self.writeln('    DWORD nLength;')
        self.writeln('    void *lpSecurityDescriptor;')
        self.writeln('    BOOL bInheritHandle;')
        self.writeln('} SECURITY_ATTRIBUTES;')
        self.writeln()
        # IUnknown (minimal COM base)
        self.writeln('typedef struct IUnknown {')
        self.writeln('    void *lpVtbl;')
        self.writeln('} IUnknown;')
        self.writeln()
        self.writeln('#endif /* native Linux */')
        self.writeln()

    def emit_forward_declarations(self):
        """Emit forward declarations for all interfaces, structs, and unions.

        By forward-declaring every struct/union with
        ``typedef struct X X;`` before any definitions, we avoid problems
        with self-referential types and ordering dependencies.
        """
        self.writeln('/* Interface forward declarations */')
        for iface in self.reg.interfaces:
            if iface.name == 'IUnknown':
                continue
            self.writeln(f'typedef struct {iface.name} {iface.name};')
        self.writeln()

        # Interface aliases (e.g. ID3DBlob -> ID3D10Blob)
        iface_aliases = []
        for ty in self.reg.aliases:
            if not ty.name or not ty.alias_target:
                continue
            target = self.reg.get_type(ty.alias_target)
            if target and target.category == Category.INTERFACE:
                iface_aliases.append(ty)
        if iface_aliases:
            self.writeln('/* Interface aliases */')
            for ty in iface_aliases:
                self.writeln(f'typedef {ty.alias_target} {ty.name};')
            self.writeln()

        self.writeln('/* Struct/union forward declarations */')
        all_ordered = collect_struct_types(self.reg)
        for ntype in all_ordered:
            if not ntype.name:
                continue
            if '__anon_' in ntype.name:
                continue
            if ntype.name in PREAMBLE_STRUCT_NAMES:
                continue
            kind = 'union' if ntype.category == Category.UNION else 'struct'
            # Some Win32 types (LUID, SIZE, HDC, ...) come from windows.h on
            # MinGW with different struct tags, so re-typedef'ing them
            # conflicts.  Skip those names on MinGW.
            if ntype.name in WIN32_BASE_NAMES:
                self.writeln(f'#ifndef __MINGW32__')
                self.writeln(f'typedef {kind} {ntype.name} {ntype.name};')
                self.writeln(f'#endif')
            else:
                self.writeln(f'typedef {kind} {ntype.name} {ntype.name};')
        self.writeln()

        # Anonymous type typedefs are emitted after struct bodies (below)

    def emit_undefined_placeholders(self):
        """Emit placeholder declarations for types referenced but not defined."""
        if not self._undefined_types:
            return
        self.writeln('/* Placeholder types (referenced but not in protocol JSON) */')
        for name in sorted(self._undefined_types):
            print(f'  WARNING: undefined type {name} — emitting placeholder',
                  file=sys.stderr)
            # On MinGW some "undefined" types like HDC are actually provided
            # by windows.h (just with a different definition).  Skip them
            # there to avoid conflicts.
            if name in WIN32_BASE_NAMES:
                self.writeln(f'#ifndef __MINGW32__')
                self.writeln(f'typedef int {name}; /* placeholder */')
                self.writeln(f'#endif')
            else:
                self.writeln(f'typedef int {name}; /* placeholder */')
        self.writeln()

    def emit_constants(self):
        if not self.reg.consts:
            return
        self.writeln('/* Constants */')
        for c in self.reg.consts:
            if c.name and c.value is not None:
                if c.value > 0xFFFF:
                    self.writeln(f'#define {c.name} 0x{c.value:X}')
                else:
                    self.writeln(f'#define {c.name} {c.value}')
        self.writeln()

    def emit_enums(self):
        if not self.reg.enums:
            return
        self.writeln('/* Enums */')
        self.writeln()
        for ty in self.reg.enums:
            if not ty.name:
                continue
            self.writeln(f'typedef enum {ty.name} {{')
            for field in ty.fields:
                if field.name and field.value is not None:
                    val = field.value
                    if val < 0:
                        val_str = str(val)
                    elif val > 0xFFFF:
                        val_str = f'0x{val:X}'
                    else:
                        val_str = str(val)
                    self.writeln(f'    {field.name} = {val_str},')
            self.writeln(f'}} {ty.name};')
            self.writeln()

    def emit_aliases(self):
        """Emit type aliases.  DirectX aliases (D3D12_RECT, DXGI_USAGE, etc.)
        are emitted unconditionally; Windows SDK base type aliases are skipped
        (already in the #ifndef _WIN32 block)."""
        alias_types = []
        alias_set = set()

        def add_alias(ty):
            if ty.name in alias_set:
                return
            alias_set.add(ty.name)
            target = self.reg.get_type(ty.alias_target)
            if target and target.category == Category.ALIAS and target.name not in alias_set:
                add_alias(target)
            alias_types.append(ty)

        for ty in self.reg.aliases:
            if not ty.name or not ty.alias_target:
                continue
            # Skip everything already emitted elsewhere or C keywords
            if ty.name in PREAMBLE_NAMES:
                continue
            if ty.name in ('int', 'float', 'char', 'void', 'long', 'short',
                           'unsigned', 'signed', 'double'):
                continue
            # Skip interface aliases (emitted in forward declarations)
            target = self.reg.get_type(ty.alias_target)
            if target and target.category == Category.INTERFACE:
                continue
            add_alias(ty)

        if not alias_types:
            return

        self.writeln('/* Type aliases */')
        for ty in alias_types:
            # HRESULT etc. come from windows.h on MinGW with a different
            # underlying type (LONG vs int32_t).  Skip on MinGW.
            if ty.name in WIN32_BASE_NAMES:
                self.writeln(f'#ifndef __MINGW32__')
                self.writeln(f'typedef {ty.alias_target} {ty.name};')
                self.writeln(f'#endif')
            else:
                self.writeln(f'typedef {ty.alias_target} {ty.name};')
        self.writeln()

    def emit_structs_unions(self):
        all_ordered = collect_struct_types(self.reg)
        self.writeln('/* Structs and unions */')
        self.writeln()
        for ntype in all_ordered:
            if not ntype.name:
                continue
            # Skip anonymous synthetic types — they get inlined
            if '__anon_' in ntype.name:
                continue
            # Skip built-in types already emitted in preamble
            if ntype.name in PREAMBLE_STRUCT_NAMES:
                continue

            kind = 'union' if ntype.category == Category.UNION else 'struct'
            # Wrap WIN32_BASE_NAMES struct definitions in #ifndef __MINGW32__
            # because windows.h defines them with different struct tags.
            wrap_mingw = ntype.name in WIN32_BASE_NAMES
            if wrap_mingw:
                self.writeln('#ifndef __MINGW32__')
            self.writeln(f'{kind} {ntype.name} {{')
            self._emit_fields(ntype.fields, indent=1)
            self.writeln(f'}};')
            if wrap_mingw:
                self.writeln('#endif')
            self.writeln()

    def emit_anon_typedefs(self):
        """Emit typedefs for anonymous types used as named struct fields.
        These are needed by the protocol codegen's encode/decode functions."""
        any_emitted = False
        for ntype in self.reg.anonymous_types:
            if not ntype.name or '__anon_' not in ntype.name:
                continue
            if not any_emitted:
                self.writeln('/* Anonymous type typedefs (for protocol codegen) */')
                any_emitted = True
            kind = 'union' if ntype.category == Category.UNION else 'struct'
            self.writeln(f'typedef {kind} {{')
            self._emit_fields(ntype.fields, 1)
            self.writeln(f'}} {ntype.name};')
            self.writeln()
        if any_emitted:
            self.writeln()

    def emit_functions(self):
        if not self.reg.functions:
            return
        self.writeln('/* Top-level function declarations */')
        for func in self.reg.functions:
            if not func.name:
                continue
            ret = func.return_type or 'void'
            params = self._format_params(func.params)
            self.writeln(f'{ret} {func.name}({params});')
        self.writeln()

    # -------------------------------------------------------------------
    # Field / parameter emission helpers
    # -------------------------------------------------------------------

    def _emit_fields(self, fields, indent=1):
        """Emit struct/union fields with the given indentation level."""
        prefix = '    ' * indent
        for i, field in enumerate(fields):
            # Check if this field uses an anonymous inline type
            if field.type_name and '__anon_' in field.type_name:
                anon_type = self.reg.get_type(field.type_name)
                if anon_type:
                    kind = 'union' if anon_type.category == Category.UNION else 'struct'
                    if field.name:
                        self.writeln(f'{prefix}{kind} {{')
                        self._emit_fields(anon_type.fields, indent + 1)
                        self.writeln(f'{prefix}}} {field.name};')
                    else:
                        self.writeln(f'{prefix}{kind} {{')
                        self._emit_fields(anon_type.fields, indent + 1)
                        self.writeln(f'{prefix}}};')
                    continue

            type_str = self._field_type_str(field)
            name = field.name or f'_reserved_{i}'

            if field.bitwidth:
                self.writeln(f'{prefix}{type_str} {name} : {field.bitwidth};')
            elif field.indirection == 0 and isinstance(field.count, int):
                self.writeln(f'{prefix}{type_str} {name}[{field.count}];')
            elif field.indirection == 0 and isinstance(field.count, list):
                dims = ''.join(f'[{d}]' for d in field.count)
                self.writeln(f'{prefix}{type_str} {name}{dims};')
            elif field.indirection > 0:
                const = 'const ' if field.const else ''
                stars = '*' * field.indirection
                self.writeln(f'{prefix}{const}{type_str} {stars}{name};')
            else:
                self.writeln(f'{prefix}{type_str} {name};')

    def _field_type_str(self, field):
        """Return the C type string for a field, using Microsoft type names."""
        if not field.type_name or field.type_name == 'void':
            return 'void'
        return field.type_name

    def _format_params(self, params):
        """Format function parameters as a C parameter list string."""
        if not params:
            return 'void'
        parts = []
        for p in params:
            type_str = self._field_type_str(p)
            const = 'const ' if p.const else ''
            stars = '*' * p.indirection
            name = p.name or '_'
            if p.indirection > 0:
                parts.append(f'{const}{type_str} {stars}{name}')
            else:
                parts.append(f'{type_str} {name}')
        return ', '.join(parts)

    # -------------------------------------------------------------------
    # Generate
    # -------------------------------------------------------------------

    def generate(self):
        self._collect_undefined_types()
        self.emit_preamble()
        self.emit_windows_types()
        # On real Windows (MSVC) the SDK headers provide everything below.
        # On MinGW and on Linux we need our own definitions because the
        # bundled headers are incomplete.
        self.writeln('#if !defined(_WIN32) || defined(__MINGW32__)')
        self.writeln()
        self.emit_forward_declarations()
        self.emit_undefined_placeholders()
        self.emit_constants()
        self.emit_enums()
        self.emit_aliases()
        self.emit_structs_unions()
        self.emit_anon_typedefs()
        self.emit_functions()
        self.writeln('#endif /* !_WIN32 || __MINGW32__ */')
        self.writeln()
        self.emit_footer()
        return self.result()


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate Microsoft DirectX-compatible C header from npt_registry.json')
    parser.add_argument('--json', required=True, type=Path,
                        help='Path to npt_registry.json')
    parser.add_argument('--overlay', action='append', type=Path, default=[],
                        help='Path to overlay JSON (can be repeated)')
    parser.add_argument('--output', required=True, type=Path,
                        help='Output header file path')
    args = parser.parse_args()

    registry = TypeRegistry()
    registry.load(args.json, args.overlay)
    registry.resolve()

    print(f'Loaded: {len(registry.interfaces)} interfaces, '
          f'{len(registry.enums)} enums, '
          f'{len(registry.structs)} structs, '
          f'{len(registry.unions)} unions, '
          f'{len(registry.consts)} consts, '
          f'{len(registry.aliases)} aliases, '
          f'{len(registry.functions)} functions')

    writer = HeaderWriter(registry)
    content = writer.generate()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    print(f'Wrote {args.output} ({len(content)} bytes)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
