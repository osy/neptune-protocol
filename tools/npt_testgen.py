#!/usr/bin/env python3

# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

"""
Neptune protocol test generator.

Standalone tool that reads npt_registry.json + overlay and generates C
roundtrip tests exercising encode/decode for all structs and interface
methods.  Does NOT import from npt_registry.py or npt_codegen.py.

Produces four files:
  - npt_test_ids.h         -- test ID #defines and style enum
  - test_roundtrip_host.c  -- host-side struct tests, command verify, reply encode
  - test_roundtrip_guest.c -- guest-side command encode, reply verify
  - test_roundtrip.c       -- main runner
"""

import argparse
import json
import re
import sys
from io import StringIO
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants (replicated independently from npt_registry.py)
# ---------------------------------------------------------------------------

PRIMITIVE_NAMES = {
    'uint8_t', 'int8_t', 'uint16_t', 'int16_t',
    'uint32_t', 'int32_t', 'uint64_t', 'int64_t',
    'float', 'double',
}

PRIMITIVE_WIRE_SIZES = {
    'uint8_t': 4, 'int8_t': 4, 'uint16_t': 4, 'int16_t': 4,
    'uint32_t': 4, 'int32_t': 4, 'float': 4,
    'uint64_t': 8, 'int64_t': 8, 'double': 8,
}

STRING_TYPES = {'CHAR', 'char'}
WSTRING_TYPES = {'WCHAR', 'wchar_t'}
NON_SERIALIZABLE_TYPES = {'void', 'VOID', 'PFN_DESTRUCTION_CALLBACK',
                          'SECURITY_ATTRIBUTES', 'HDC'}

_VOID_RETURN_TYPES = {'VOID', 'void', None, ''}


# ---------------------------------------------------------------------------
# Overlay merge (replicated independently)
# ---------------------------------------------------------------------------

_TYPED_ARRAY_KEYS = {'types', 'fields', 'methods', 'params'}


def _find_match(base_arr, ov_elem):
    if 'index' in ov_elem:
        idx = ov_elem['index']
        if 0 <= idx < len(base_arr):
            return idx
        return None
    if 'name' in ov_elem and ov_elem['name'] is not None:
        for i, base_elem in enumerate(base_arr):
            if isinstance(base_elem, dict) and base_elem.get('name') == ov_elem['name']:
                return i
    return None


# NOTE: _find_match / _merge_objects / _merge_typed_array / merge_overlay
# are duplicated in tools/npt_registry.py — keep them in sync.
def _merge_objects(base_obj, ov_obj):
    for key, ov_val in ov_obj.items():
        if key == 'index':
            continue
        base_val = base_obj.get(key)
        # Deep-merge nested type definitions (e.g. anonymous inline union/
        # struct on a struct field): the overlay names just the changed
        # members, the base keeps `primitive`, untouched fields, etc.
        if (key == 'type'
                and isinstance(ov_val, dict)
                and isinstance(base_val, dict)):
            _merge_objects(base_val, ov_val)
            continue
        if key in base_obj and key in _TYPED_ARRAY_KEYS and isinstance(ov_val, list):
            _merge_typed_array(base_obj[key], ov_val)
        else:
            base_obj[key] = ov_val


def _merge_typed_array(base_arr, ov_arr):
    for ov_elem in ov_arr:
        if not isinstance(ov_elem, dict):
            continue
        match_idx = _find_match(base_arr, ov_elem)
        if match_idx is not None:
            _merge_objects(base_arr[match_idx], ov_elem)
        else:
            base_arr.append(ov_elem)


def merge_overlay(base, overlay):
    if base.get('version') != overlay.get('version'):
        raise ValueError(f"Version mismatch: base={base.get('version')} "
                         f"overlay={overlay.get('version')}")
    _merge_typed_array(base.setdefault('types', []), overlay.get('types', []))


# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------

def parse_uuid(uuid_str):
    clean = uuid_str.replace('-', '')
    return bytes.fromhex(clean)


def uuid_hash(uuid_bytes):
    h = 0
    for b in uuid_bytes:
        h ^= b
    return h & 0xFF



# ---------------------------------------------------------------------------
# Type registry (minimal, self-contained)
# ---------------------------------------------------------------------------

def _strip_type_prefix(name):
    for prefix in ('struct ', 'union ', 'enum '):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


class Field:
    __slots__ = ('name', 'type_name', 'inline_type', 'indirection', 'const',
                 'count', 'count_output', 'bitwidth', 'condition', 'value',
                 'handle', 'input', 'output', 'optional')

    def __init__(self, raw, parent_name=None, index=0):
        self.name = raw.get('name')
        type_val = raw.get('type', 'void')
        if isinstance(type_val, dict):
            self.inline_type = type_val
            self.type_name = ''
        else:
            self.inline_type = None
            self.type_name = _strip_type_prefix(type_val)
        self.indirection = raw.get('indirection', 0)
        self.const = raw.get('const', False)
        self.count = raw.get('count')
        self.count_output = raw.get('count_output')
        self.bitwidth = raw.get('bitwidth')
        self.condition = raw.get('condition')
        self.value = raw.get('value')
        self.handle = raw.get('handle')
        self.input = raw.get('input', True)
        self.output = raw.get('output', False)
        self.optional = raw.get('optional', False)


class Method:
    __slots__ = ('name', 'return_type', 'params', 'wire_index', 'id',
                 'skip_default')

    def __init__(self, raw, index):
        self.name = raw['name']
        self.return_type = raw.get('return')
        self.params = [Field(p, parent_name=self.name, index=i)
                       for i, p in enumerate(raw.get('params', []))]
        self.wire_index = raw.get('index', index)
        self.id = raw.get('id')


class TypeInfo:
    __slots__ = ('name', 'primitive', 'fields', 'methods', 'parent_name',
                 'uuid', 'uuid_hash', 'uuid_bytes', 'return_type', 'group',
                 'id', 'params', 'alias_target', 'is_anonymous', 'value')

    def __init__(self, name, primitive):
        self.name = name
        self.primitive = primitive
        self.fields = []
        self.methods = []
        self.parent_name = None
        self.uuid = None
        self.uuid_hash = 0
        self.uuid_bytes = None
        self.return_type = None
        self.group = None
        self.id = None
        self.params = []
        self.alias_target = None
        self.is_anonymous = False
        self.value = None

    @property
    def category(self):
        if self.primitive in PRIMITIVE_NAMES:
            if self.name == self.primitive:
                return 'primitive'
            return 'alias'
        if self.primitive == 'enum':
            return 'enum'
        if self.primitive == 'struct':
            return 'struct'
        if self.primitive == 'union':
            return 'union'
        if self.primitive == 'interface':
            return 'interface'
        if self.primitive == 'function':
            return 'function'
        if self.primitive == 'const':
            return 'const'
        return 'alias'


class Registry:
    """Minimal self-contained type registry."""

    def __init__(self):
        self.types = {}
        self.interfaces = []
        self.functions = []
        self.structs = []
        self.unions = []
        self.anonymous_types = []

    def load(self, json_path, overlay_paths=None):
        with open(json_path, 'r') as f:
            base = json.load(f)
        for overlay_path in (overlay_paths or []):
            with open(overlay_path, 'r') as f:
                overlay = json.load(f)
            merge_overlay(base, overlay)
        self._build(base)

    def _categorize(self, prim, name=None):
        if prim in PRIMITIVE_NAMES:
            if name is None or name == prim:
                return 'primitive'
            return 'alias'
        return {
            'enum': 'enum', 'struct': 'struct', 'union': 'union',
            'interface': 'interface', 'function': 'function', 'const': 'const',
        }.get(prim, 'alias')

    def _build(self, data):
        for raw in data.get('types', []):
            name = raw.get('name')
            prim = raw.get('primitive', '')
            cat = self._categorize(prim, name)

            t = TypeInfo(name, prim)

            if cat == 'alias':
                t.alias_target = prim
            elif cat == 'enum':
                t.fields = [Field(f, parent_name=name, index=i)
                            for i, f in enumerate(raw.get('fields', []))]
            elif cat in ('struct', 'union'):
                t.fields = [Field(f, parent_name=name, index=i)
                            for i, f in enumerate(raw.get('fields', []))]
            elif cat == 'interface':
                t.parent_name = raw.get('parent')
                t.uuid = raw.get('uuid')
                if t.uuid:
                    t.uuid_bytes = parse_uuid(t.uuid)
                    t.uuid_hash = uuid_hash(t.uuid_bytes)
                t.methods = [Method(m, i)
                             for i, m in enumerate(raw.get('methods', []))]
            elif cat == 'function':
                t.return_type = raw.get('return')
                t.group = raw.get('group')
                t.id = raw.get('id')
                t.params = [Field(p, parent_name=name, index=i)
                            for i, p in enumerate(raw.get('params', []))]
            elif cat == 'const':
                t.value = raw.get('value')

            if name:
                self.types[name] = t

        # Built-ins
        if 'IUnknown' not in self.types:
            iu = TypeInfo('IUnknown', 'interface')
            iu.uuid = '00000000-0000-0000-c000-000000000046'
            iu.uuid_bytes = parse_uuid(iu.uuid)
            iu.uuid_hash = uuid_hash(iu.uuid_bytes)
            self.types['IUnknown'] = iu
        for bname in ('GUID', 'POINT', 'RECT'):
            if bname not in self.types:
                self.types[bname] = TypeInfo(bname, 'struct')

        # Resolve anonymous inline types
        self._resolve_anonymous()

        # Build lists
        for t in self.types.values():
            cat = t.category
            if cat == 'interface':
                self.interfaces.append(t)
            elif cat == 'function':
                if t.group is not None and t.id is not None:
                    self.functions.append(t)
            elif cat == 'struct':
                self.structs.append(t)
            elif cat == 'union':
                self.unions.append(t)

        self.functions.sort(key=lambda f: (f.group, f.id))

    def _resolve_anonymous(self):
        types_to_add = {}

        def process_fields(fields, parent_name):
            for i, field in enumerate(fields):
                if field.inline_type is not None:
                    synth_name = f'{parent_name}__anon_{i}'
                    prim = field.inline_type.get('primitive', 'struct')
                    synth = TypeInfo(synth_name, prim)
                    synth.fields = [Field(f, parent_name=synth_name, index=j)
                                    for j, f in enumerate(
                                        field.inline_type.get('fields', []))]
                    synth.is_anonymous = True
                    types_to_add[synth_name] = synth
                    self.anonymous_types.append(synth)
                    field.type_name = synth_name
                    field.inline_type = None
                    process_fields(synth.fields, synth_name)

        for t in list(self.types.values()):
            if t.category in ('struct', 'union') and t.name:
                process_fields(t.fields, t.name)

        self.types.update(types_to_add)

    def resolve_alias_chain(self, type_name):
        visited = set()
        current = type_name
        while current and current not in visited:
            visited.add(current)
            t = self.types.get(current)
            if t is None:
                return current
            if t.category == 'alias' and t.alias_target:
                current = t.alias_target
            else:
                return current
        return current

    def is_interface_type(self, type_name):
        t = self.types.get(type_name)
        return t is not None and t.category == 'interface'

    def is_string_type(self, field):
        if field.indirection != 1 or field.count is not None:
            return False
        if field.type_name in STRING_TYPES:
            return True
        t = self.types.get(field.type_name)
        if t and t.category == 'alias' and t.alias_target in STRING_TYPES:
            return True
        return False

    def is_wstring_type(self, field):
        if field.indirection != 1 or field.count is not None:
            return False
        if field.type_name in WSTRING_TYPES:
            return True
        t = self.types.get(field.type_name)
        if t and t.category == 'alias' and t.alias_target in WSTRING_TYPES:
            return True
        return False

    def is_enum(self, field):
        t = self.types.get(field.type_name)
        return t is not None and t.category == 'enum'

    def is_struct_or_union(self, field):
        t = self.types.get(field.type_name)
        return t is not None and t.category in ('struct', 'union')


# ---------------------------------------------------------------------------
# Field classification
# ---------------------------------------------------------------------------

def _is_fixed_array(field):
    if isinstance(field.count, int) or isinstance(field.count, list):
        return True
    if isinstance(field.count, str) and field.count.strip().isdigit():
        return True
    return False


def _is_wide_string_field(reg, field):
    if field.type_name in WSTRING_TYPES:
        return True
    t = reg.types.get(field.type_name)
    if t and t.category == 'alias' and t.alias_target in WSTRING_TYPES:
        return True
    return False


def _is_string_array(reg, field):
    if field.indirection != 2 or field.count is None:
        return False
    if field.type_name in STRING_TYPES or field.type_name in WSTRING_TYPES:
        return True
    t = reg.types.get(field.type_name)
    if t and t.category == 'alias':
        if t.alias_target in STRING_TYPES or t.alias_target in WSTRING_TYPES:
            return True
    return False


def classify_field(reg, field):
    """Classify a field into one of the known categories.
    Returns a string tag."""
    # NON_SERIALIZABLE
    if (field.type_name in NON_SERIALIZABLE_TYPES and field.indirection >= 1
            and field.count is None and field.handle is None):
        return 'NON_SERIALIZABLE'

    # BITFIELD
    if field.bitwidth is not None and field.name is not None:
        return 'BITFIELD'

    # ANONYMOUS_STRUCT/UNION
    if field.name is None:
        t = reg.types.get(field.type_name)
        if t and t.category in ('struct', 'union'):
            return 'ANONYMOUS_INLINE'

    # COM_HANDLE (single)
    if field.handle == 'com' and not (field.indirection >= 2 and field.count):
        return 'COM_HANDLE'

    # WIN32_HANDLE
    if field.handle == 'win32':
        return 'WIN32_HANDLE'

    # COM_HANDLE_ARRAY
    if field.handle == 'com' and field.indirection >= 2 and field.count is not None:
        return 'COM_HANDLE_ARRAY'

    # INTERFACE_REF
    if (field.indirection >= 1 and reg.is_interface_type(field.type_name)
            and not (field.indirection >= 2 and field.count)):
        return 'INTERFACE_REF'

    # FIXED_ARRAY
    if field.indirection == 0 and _is_fixed_array(field):
        return 'FIXED_ARRAY'

    # SCALAR
    if field.indirection == 0 and field.count is None:
        return 'SCALAR'

    # STRING_ARRAY
    if _is_string_array(reg, field):
        return 'STRING_ARRAY'

    # STRING
    if reg.is_string_type(field):
        return 'STRING'

    # WSTRING
    if reg.is_wstring_type(field):
        return 'WSTRING'

    # BLOB
    if (field.type_name in ('void', 'VOID') and field.indirection == 1
            and field.count is not None):
        return 'BLOB'

    # COUNTED_ARRAY (only indirection == 1; indirection >= 2 non-string
    # non-COM arrays are not properly encodable and treated as UNSIZED)
    if field.indirection == 1 and field.count is not None:
        return 'COUNTED_ARRAY'

    # SIMPLE_POINTER
    if field.indirection >= 1 and field.count is None:
        return 'SIMPLE_POINTER'

    return 'UNSIZED'


# ---------------------------------------------------------------------------
# Count expression helpers
# ---------------------------------------------------------------------------

def _parse_size_string(size_str):
    m = re.match(r'^_Inexpressible_\((.+)\)$', size_str)
    if m:
        inner = m.group(1)
        if inner.startswith('"'):
            return None
        return inner
    if size_str.startswith('_'):
        return None
    return size_str


def _resolve_size_term(term, prefix, fields_map):
    term = term.strip()
    if term.isdigit():
        return term
    if term.startswith('sizeof('):
        return term
    if '->' in term:
        parts = term.split('->', 1)
        return f'{prefix}{parts[0]}->{parts[1]}'
    deref = fields_map.get(term, -1)
    if deref < 0:
        return term
    return f'{"*" * deref}{prefix}{term}'


def _build_fields_map(fields, reg):
    """Build map field_name -> indirection for fields accessible as siblings."""
    fmap = {}

    def collect(flist):
        for f in flist:
            if f.name:
                fmap[f.name] = f.indirection
            if f.name is None:
                t = reg.types.get(f.type_name)
                if t and t.category in ('struct', 'union'):
                    collect(t.fields)
    collect(fields)
    return fmap


def get_count_expr(field, prefix, fields_map):
    """Get the C expression for the array count of a field."""
    size = field.count
    if size is None:
        return None
    if isinstance(size, int):
        return str(size)
    if isinstance(size, list):
        return ' * '.join(str(d) for d in size)
    if isinstance(size, str):
        parsed = _parse_size_string(size)
        if parsed is None:
            return None
        if parsed.isdigit():
            return parsed
        terms = [t.strip() for t in parsed.split('*')]
        c_terms = [_resolve_size_term(t, prefix, fields_map) for t in terms]
        return ' * '.join(c_terms)
    return None


def get_output_count_expr(field, prefix, fields_map):
    if field.count_output:
        deref = fields_map.get(field.count_output, -1)
        if deref < 0:
            return field.count_output
        return f'{"*" * deref}{prefix}{field.count_output}'
    return get_count_expr(field, prefix, fields_map)


def _count_field_after_array(array_field, output_params):
    """Check if the count field for array_field appears after it in
    the output_params list.  Returns the count param if so, else None."""
    count_name = array_field.count
    if not isinstance(count_name, str):
        return None
    parsed = _parse_size_string(count_name)
    if parsed is None or parsed.isdigit():
        return None
    # Only handle simple single-field counts (not multiplications)
    if '*' in parsed:
        return None
    # Find the positions
    array_idx = None
    count_idx = None
    count_param = None
    for i, p in enumerate(output_params):
        if p is array_field:
            array_idx = i
        if p.name == parsed:
            count_idx = i
            count_param = p
    if array_idx is not None and count_idx is not None and count_idx > array_idx:
        return count_param
    return None



# ---------------------------------------------------------------------------
# Return type helpers
# ---------------------------------------------------------------------------

def has_return(ret_type):
    return ret_type and ret_type not in _VOID_RETURN_TYPES


def is_scalar_return(reg, ret_type):
    if not has_return(ret_type):
        return False
    ref = reg.types.get(ret_type)
    if ref and ref.category == 'enum':
        return True
    base = reg.resolve_alias_chain(ret_type)
    wire = PRIMITIVE_WIRE_SIZES.get(base)
    return wire is not None and wire <= 4


# ---------------------------------------------------------------------------
# Skip logic for structs
# ---------------------------------------------------------------------------

def should_skip_struct(reg, t):
    """Return (skip, reason) for a struct/union type."""
    for field in t.fields:
        if field.optional:
            continue
        cls = classify_field(reg, field)
        if cls == 'NON_SERIALIZABLE':
            return True, f"field '{field.name}' is non-serializable ({field.type_name})"
        if cls == 'UNSIZED':
            return True, f"field '{field.name}' is unsized"
        # Check _Inexpressible_ with quoted string
        if isinstance(field.count, str):
            m = re.match(r'^_Inexpressible_\((.+)\)$', field.count)
            if m and m.group(1).startswith('"'):
                return True, f"field '{field.name}' has _Inexpressible_ quoted count"
        # Check for anonymous inline that itself has problems
        if field.name is None:
            t2 = reg.types.get(field.type_name)
            if t2 and t2.category in ('struct', 'union'):
                skip, reason = should_skip_struct(reg, t2)
                if skip:
                    return True, f"anonymous inline: {reason}"
    # Recursively check if any referenced struct type is untestable.
    if _contains_untestable_type(reg, t, set()):
        return True, "contains type with untestable fields"
    return False, ''


def _contains_untestable_type(reg, t, visited):
    """Recursively check if type contains an incompatible anonymous union
    or a non-serializable field in a referenced struct."""
    if t.name in visited:
        return False
    visited.add(t.name)
    for field in t.fields:
        # Check anonymous inline unions
        if field.name is None:
            t2 = reg.types.get(field.type_name) if field.type_name else None
            if t2 and t2.category == 'union':
                if not _anon_union_members_compatible(reg, t2):
                    return True
        # Check if this field itself is non-serializable (but not optional)
        cls = classify_field(reg, field)
        if cls == 'NON_SERIALIZABLE' and not field.optional:
            return True
        # Check referenced struct types (including pointer targets)
        t2 = reg.types.get(field.type_name) if field.type_name else None
        if t2 and t2.category in ('struct', 'union') \
                and t2.name not in BUILTIN_STRUCT_NAMES \
                and not t2.is_anonymous:
            if _contains_untestable_type(reg, t2, visited):
                return True
    return False


def _get_anon_unions(reg, t):
    """Return list of (anon_field, anon_type) for anonymous union fields in a struct."""
    result = []
    for field in t.fields:
        if field.name is not None:
            continue
        t2 = reg.types.get(field.type_name) if field.type_name else None
        if t2 and t2.category == 'union' and t2.fields:
            result.append((field, t2))
    return result


def _struct_has_anon_union(reg, t):
    """Check if struct has any anonymous union fields."""
    return len(_get_anon_unions(reg, t)) > 0


def _anon_union_members_compatible(reg, anon_type):
    """Check if all members of an anonymous union have compatible wire formats.
    Members are compatible if they are all the same type, all scalars/enums,
    or all value-only (no pointers and same size)."""
    if len(anon_type.fields) <= 1:
        return True
    # Check if any member has pointer fields
    has_ptr = False
    member_types = set()
    for mf in anon_type.fields:
        member_types.add(mf.type_name)
        if mf.indirection >= 1:
            has_ptr = True
        mt = reg.types.get(mf.type_name)
        if mt and mt.category in ('struct', 'union'):
            for sf in mt.fields:
                if sf.indirection >= 1:
                    has_ptr = True
    # If all members are the same type, compatible
    if len(member_types) == 1:
        return True
    # If any member has pointers, different types are incompatible
    if has_ptr:
        return False
    # Check if any member is a struct with bitfields. The encode-all-members
    # approach writes each bitfield member as a separate uint32_t AND writes
    # the overlapping scalar member. After decode, the scalar write overwrites
    # the bitfield writes, but compiler-specific bitfield packing can cause
    # subtle mismatch in some contexts.
    for mf in anon_type.fields:
        mt = reg.types.get(mf.type_name)
        if mt and mt.category in ('struct', 'union'):
            if any(sf.bitwidth is not None for sf in mt.fields):
                return False
    return True



# ---------------------------------------------------------------------------
# Skip logic for methods
# ---------------------------------------------------------------------------

def should_skip_method(reg, method):
    """Return (skip, reason) for a method."""
    # Check return type
    ret_type = method.return_type if hasattr(method, 'return_type') else None
    if ret_type:
        rt = reg.types.get(ret_type)
        if rt and rt.category in ('struct', 'union') and not rt.is_anonymous \
                and rt.name not in BUILTIN_STRUCT_NAMES:
            skip, reason = should_skip_struct(reg, rt)
            if skip:
                return True, f"return type {ret_type}: {reason}"
    for p in method.params:
        cls = classify_field(reg, p)
        if cls == 'NON_SERIALIZABLE' and not p.optional:
            return True, f"param '{p.name}' is non-serializable"
        if cls == 'UNSIZED' and not p.optional:
            return True, f"param '{p.name}' is unsized"
        # Check if param's struct type is untestable (transitively)
        t2 = reg.types.get(p.type_name)
        if t2 and t2.category in ('struct', 'union') and not t2.is_anonymous \
                and t2.name not in BUILTIN_STRUCT_NAMES:
            skip, reason = should_skip_struct(reg, t2)
            if skip:
                return True, f"param '{p.name}' type {p.type_name}: {reason}"
        if isinstance(p.count, str):
            m = re.match(r'^_Inexpressible_\((.+)\)$', p.count)
            if m and m.group(1).startswith('"'):
                if not p.optional:
                    return True, f"param '{p.name}' has _Inexpressible_ quoted count"
    return False, ''


# ---------------------------------------------------------------------------
# Struct init generation
# ---------------------------------------------------------------------------

def _find_count_fields(fields, reg):
    """Find which fields are referenced as count by other fields.
    Returns map: count_field_name -> [dependent fields]."""
    count_map = {}
    for field in fields:
        if isinstance(field.count, str):
            parsed = _parse_size_string(field.count)
            if parsed and not parsed.isdigit():
                terms = [t.strip() for t in parsed.split('*')]
                for term in terms:
                    # Skip member-access terms (e.g., pDesc->MipLevels):
                    # pDesc is a struct pointer used to access a member,
                    # not a standalone count field.
                    if '->' in term:
                        continue
                    if not term.isdigit() and not term.startswith('sizeof('):
                        count_map.setdefault(term, []).append(field)
        if field.count_output:
            count_map.setdefault(field.count_output, []).append(field)
    return count_map


def gen_struct_init(out, reg, t, member_name=None, anon_variant=None):
    """Generate init function for a struct (or a specific union member).

    anon_variant: if set, (anon_type_name, chosen_member_name) for structs
    with anonymous unions. Only the chosen member is initialized; other
    members' pointer fields are zeroed to prevent unsafe dereferences.
    """
    sname = t.name
    if member_name:
        suffix = f'__{member_name}'
    elif anon_variant:
        suffix = f'__{anon_variant[1]}'
    else:
        suffix = ''
    func_name = f'init_{sname}{suffix}'

    fields = t.fields
    if member_name:
        fields = [f for f in t.fields if f.name == member_name]

    out.write(f'static void {func_name}({sname} *val, int style, '
              f'uint32_t *seed, int randomize)\n{{\n')
    out.write(f'    if (randomize) npt_test_fill(val, sizeof(*val), seed);\n')

    # Flatten anonymous inline fields into the processing list.
    # For anonymous unions: zero inactive members, only init chosen variant.
    expanded_fields = []
    for field in fields:
        if field.name is None:
            t2 = reg.types.get(field.type_name)
            if not t2:
                continue
            if t2.category == 'union' and t2.fields:
                chosen_name = None
                if anon_variant and anon_variant[0] == field.type_name:
                    chosen_name = anon_variant[1]
                elif _anon_union_members_compatible(reg, t2):
                    chosen_name = t2.fields[0].name if t2.fields[0].name else None
                else:
                    # Incompatible union: NULL all pointer members, skip init
                    for mf in t2.fields:
                        if mf.name and mf.indirection >= 1:
                            out.write(f'    val->{mf.name} = NULL;\n')
                    chosen_name = None

                # Only add the chosen member to the processing list
                if chosen_name:
                    for mf in t2.fields:
                        if mf.name == chosen_name:
                            expanded_fields.append(mf)
                            break
            elif t2.category == 'struct' and t2.fields:
                # Anonymous inline struct: add all sub-fields
                for sf in t2.fields:
                    if sf.name:
                        expanded_fields.append(sf)
        else:
            expanded_fields.append(field)

    # Build count_map and fields_map from expanded fields
    count_map = _find_count_fields(expanded_fields, reg)
    fields_map = _build_fields_map(expanded_fields, reg)

    # Pass 1: set count fields
    for field in expanded_fields:
        if field.name is None:
            continue
        if field.name in count_map:
            out.write(f'    /* count field: {field.name} */\n')
            out.write(f'    switch (style) {{\n')
            out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NONNULL:\n')
            out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NULL:\n')
            out.write(f'        val->{field.name} = 0;\n')
            out.write(f'        break;\n')
            out.write(f'    case NPT_STYLE_COUNT_ONE:\n')
            out.write(f'        val->{field.name} = 1;\n')
            out.write(f'        break;\n')
            out.write(f'    case NPT_STYLE_COUNT_NONZERO:\n')
            out.write(f'    default:\n')
            out.write(f'        val->{field.name} = 5;\n')
            out.write(f'        break;\n')
            out.write(f'    }}\n')

    # Pass 2: fix up other fields (including expanded anonymous members)
    for field in expanded_fields:
        if field.name is None:
            continue

        if field.name in count_map:
            continue  # already handled

        cls = classify_field(reg, field)

        if cls == 'NON_SERIALIZABLE':
            if field.optional:
                out.write(f'    val->{field.name} = NULL; /* non-serializable, skip */\n')
            continue

        if cls == 'BITFIELD':
            mask = (1 << field.bitwidth) - 1
            out.write(f'    val->{field.name} &= 0x{mask:x}u;\n')
            continue

        if cls == 'COM_HANDLE':
            if field.indirection >= 1:
                out.write(f'    val->{field.name} = npt_test_handle_create(seed);\n')
            else:
                out.write(f'    val->{field.name} = '
                          f'({field.type_name})(uintptr_t)npt_test_handle_create(seed);\n')
            continue

        if cls == 'WIN32_HANDLE':
            if field.indirection >= 1:
                out.write(f'    val->{field.name} = npt_test_handle_create(seed);\n')
            else:
                out.write(f'    val->{field.name} = '
                          f'({field.type_name})(uintptr_t)npt_test_handle_create(seed);\n')
            continue

        if cls == 'INTERFACE_REF':
            out.write(f'    val->{field.name} = npt_test_handle_create(seed);\n')
            continue

        if cls == 'COM_HANDLE_ARRAY':
            cnt = get_count_expr(field, 'val->', fields_map)
            if cnt:
                out.write(f'    if ({cnt} > 0) {{\n')
                out.write(f'        val->{field.name} = npt_test_alloc(sizeof(void *) * {cnt});\n')
                out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                out.write(f'            val->{field.name}[_i] = npt_test_handle_create(seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        val->{field.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }}\n')
            else:
                out.write(f'    val->{field.name} = npt_test_handle_create(seed);\n')
            continue

        if cls == 'STRING':
            out.write(f'    val->{field.name} = ({field.type_name} *)npt_test_string(seed, 8);\n')
            continue

        if cls == 'WSTRING':
            out.write(f'    val->{field.name} = ({field.type_name} *)npt_test_wstring(seed, 8);\n')
            continue

        if cls == 'STRING_ARRAY':
            cnt = get_count_expr(field, 'val->', fields_map)
            is_wide = _is_wide_string_field(reg, field)
            str_fn = 'npt_test_wstring' if is_wide else 'npt_test_string'
            out.write(f'    if ({cnt} > 0) {{\n')
            out.write(f'        val->{field.name} = npt_test_alloc(sizeof(void *) * {cnt});\n')
            out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
            out.write(f'            val->{field.name}[_i] = ({field.type_name} *){str_fn}(seed, 6);\n')
            out.write(f'    }} else {{\n')
            out.write(f'        val->{field.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
            out.write(f'    }}\n')
            continue

        if cls == 'BLOB':
            cnt = get_count_expr(field, 'val->', fields_map)
            if cnt:
                out.write(f'    if ({cnt} > 0) {{\n')
                out.write(f'        val->{field.name} = npt_test_alloc({cnt});\n')
                out.write(f'        npt_test_fill((void *)val->{field.name}, {cnt}, seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        val->{field.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }}\n')
            else:
                out.write(f'    val->{field.name} = NULL;\n')
            continue

        if cls == 'FIXED_ARRAY':
            base = reg.resolve_alias_chain(field.type_name)
            if base not in PRIMITIVE_NAMES and not reg.is_enum(field):
                t2 = reg.types.get(field.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    cnt = get_count_expr(field, 'val->', fields_map)
                    out.write(f'    for (uint32_t _i = 0; _i < (uint32_t)({cnt}); _i++)\n')
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'        init_{field.type_name}__{mf.name}'
                                  f'(&val->{field.name}[_i], style, seed, 0);\n')
                    else:
                        out.write(f'        init_{field.type_name}'
                                  f'(&val->{field.name}[_i], style, seed, 0);\n')
            # For primitives/enums, the random fill is sufficient
            continue

        if cls == 'COUNTED_ARRAY':
            cnt = get_count_expr(field, 'val->', fields_map)
            if cnt is None:
                out.write(f'    val->{field.name} = NULL; /* unknown count */\n')
                continue
            base = reg.resolve_alias_chain(field.type_name)
            is_prim = base in PRIMITIVE_NAMES or reg.is_enum(field)
            elem_size = f'sizeof({field.type_name})'
            out.write(f'    if ({cnt} > 0) {{\n')
            out.write(f'        val->{field.name} = npt_test_alloc({elem_size} * {cnt});\n')
            if is_prim:
                out.write(f'        npt_test_fill((void *)val->{field.name}, '
                          f'{elem_size} * {cnt}, seed);\n')
            else:
                t2 = reg.types.get(field.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                        out.write(f'            init_{field.type_name}__{mf.name}'
                                  f'(&(({field.type_name} *)val->{field.name})[_i], style, seed, 1);\n')
                    else:
                        out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                        out.write(f'            init_{field.type_name}'
                                  f'(&(({field.type_name} *)val->{field.name})[_i], style, seed, 1);\n')
                else:
                    out.write(f'        npt_test_fill((void *)val->{field.name}, '
                              f'{elem_size} * {cnt}, seed);\n')
            out.write(f'    }} else {{\n')
            out.write(f'        val->{field.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
            out.write(f'    }}\n')
            continue

        if cls == 'SIMPLE_POINTER':
            base = reg.resolve_alias_chain(field.type_name)
            # Self-referential pointer (e.g., linked list pNext) → set NULL
            if field.type_name == sname:
                out.write(f'    val->{field.name} = NULL; /* self-ref */\n')
                continue
            if field.optional:
                out.write(f'    if (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) {{\n')
                out.write(f'        val->{field.name} = NULL;\n')
                out.write(f'    }} else {{\n')
                out.write(f'        val->{field.name} = npt_test_alloc(sizeof({field.type_name}));\n')
                t2 = reg.types.get(field.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'        init_{field.type_name}__{mf.name}'
                                  f'(({field.type_name} *)val->{field.name}, style, seed, 1);\n')
                    else:
                        out.write(f'        init_{field.type_name}'
                                  f'(({field.type_name} *)val->{field.name}, style, seed, 1);\n')
                else:
                    out.write(f'        npt_test_fill((void *)val->{field.name}, '
                              f'sizeof({field.type_name}), seed);\n')
                out.write(f'    }}\n')
            else:
                out.write(f'    val->{field.name} = npt_test_alloc(sizeof({field.type_name}));\n')
                t2 = reg.types.get(field.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'        init_{field.type_name}__{mf.name}'
                                  f'(({field.type_name} *)val->{field.name}, style, seed, 1);\n')
                    else:
                        out.write(f'        init_{field.type_name}'
                                  f'(({field.type_name} *)val->{field.name}, style, seed, 1);\n')
                else:
                    out.write(f'    npt_test_fill((void *)val->{field.name}, '
                              f'sizeof({field.type_name}), seed);\n')
            continue

        if cls == 'SCALAR':
            # For struct/union value types, recurse init
            t2 = reg.types.get(field.type_name)
            if t2 and t2.category in ('struct', 'union') \
                    and t2.name not in BUILTIN_STRUCT_NAMES \
                    and not t2.is_anonymous:
                if t2.category == 'union' and t2.fields:
                    mf = t2.fields[0]
                    out.write(f'    init_{field.type_name}__{mf.name}'
                              f'(&val->{field.name}, style, seed, 0);\n')
                else:
                    out.write(f'    init_{field.type_name}'
                              f'(&val->{field.name}, style, seed, 0);\n')
            # Primitives/enums/anonymous: random fill is sufficient
            continue

        # UNSIZED or unknown - skip
        if field.optional:
            out.write(f'    val->{field.name} = NULL; /* unsized optional */\n')

    out.write(f'}}\n\n')



# ---------------------------------------------------------------------------
# Struct test generation
# ---------------------------------------------------------------------------

def gen_struct_test(out, sname, suffix='', test_id_macro=None):
    """Generate test_struct_StructName function."""
    func_name = f'{sname}{suffix}'
    out.write(f'static int test_struct_{func_name}(int style)\n{{\n')
    out.write(f'    uint32_t seed = 0x12345u ^ {test_id_macro} ^ (uint32_t)style;\n')
    out.write(f'    {sname} orig;\n')
    out.write(f'    memset(&orig, 0, sizeof(orig));\n')
    out.write(f'    init_{func_name}(&orig, style, &seed, 1);\n\n')
    out.write(f'    size_t w1_size = npt_sizeof_{sname}(&orig);\n')
    out.write(f'    if (w1_size == 0) {{ fprintf(stderr, "FAIL: {func_name}: sizeof returned 0\\n"); return -1; }}\n')
    out.write(f'    uint8_t *w1 = (uint8_t *)calloc(1, w1_size);\n')
    out.write(f'    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);\n')
    out.write(f'    npt_encode_{sname}(&enc1, &orig);\n')
    out.write(f'    size_t w1_actual = npt_test_encoder_written(&enc1, w1);\n\n')
    out.write(f'    {sname} decoded;\n')
    out.write(f'    memset(&decoded, 0, sizeof(decoded));\n')
    out.write(f'    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);\n')
    out.write(f'    npt_decode_{sname}(&dec, &decoded);\n\n')
    out.write(f'    size_t w2_size = npt_sizeof_{sname}(&decoded);\n')
    out.write(f'    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);\n')
    out.write(f'    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);\n')
    out.write(f'    npt_encode_{sname}(&enc2, &decoded);\n')
    out.write(f'    size_t w2_actual = npt_test_encoder_written(&enc2, w2);\n\n')
    out.write(f'    int result = npt_wire_compare("{func_name}", w1, w1_actual, w2, w2_actual);\n')
    out.write(f'    npt_test_cleanup(&dec);\n')
    out.write(f'    free(w1); free(w2);\n')
    out.write(f'    return result;\n')
    out.write(f'}}\n\n')


# ---------------------------------------------------------------------------
# Collect testable structs and methods
# ---------------------------------------------------------------------------

BUILTIN_STRUCT_NAMES = {'GUID', 'POINT', 'RECT', 'LONG'}


def collect_testable_structs(reg):
    """Return list of (TypeInfo, member_name_or_None) for testable structs/unions."""
    result = []
    seen = set()

    # Dependency order doesn't matter for tests, we just need the list
    for t in list(reg.structs) + list(reg.unions):
        if not t.name:
            continue
        if t.name in BUILTIN_STRUCT_NAMES:
            continue
        if t.is_anonymous:
            continue
        if t.name in seen:
            continue
        seen.add(t.name)

        skip, reason = should_skip_struct(reg, t)
        if skip:
            print(f"WARNING: skipping struct {t.name}: {reason}", file=sys.stderr)
            continue

        if t.category == 'union':
            # Top-level union: one test per named member
            if not _anon_union_members_compatible(reg, t):
                print(f"WARNING: skipping union {t.name}: "
                      f"members have incompatible wire formats",
                      file=sys.stderr)
                continue
            for field in t.fields:
                if field.name:
                    result.append((t, field.name, None))
        elif _struct_has_anon_union(reg, t):
            # Struct with anonymous union(s): one test per anon union member.
            # But only if all members encode identically (same type or all
            # value-only scalars). Otherwise the encode-all-members approach
            # produces inconsistent wire data.
            anon_unions = _get_anon_unions(reg, t)
            safe = True
            for anon_field, anon_type in anon_unions:
                if not _anon_union_members_compatible(reg, anon_type):
                    safe = False
                    print(f"WARNING: skipping struct {t.name}: "
                          f"anonymous union members have incompatible wire formats",
                          file=sys.stderr)
                    break
            if not safe:
                continue
            for anon_field, anon_type in anon_unions:
                for mf in anon_type.fields:
                    if mf.name:
                        result.append((t, None, (anon_field.type_name, mf.name)))
        else:
            result.append((t, None, None))

    return result


def collect_testable_methods(reg):
    """Return list of (iface, method, fname, is_toplevel) for testable methods."""
    result = []

    for iface in reg.interfaces:
        if iface.name == 'IUnknown':
            continue
        if not iface.uuid:
            continue
        for method in iface.methods:
            skip, reason = should_skip_method(reg, method)
            if skip:
                fname = f'{iface.name}_{method.name}'
                print(f"WARNING: skipping method {fname}: {reason}",
                      file=sys.stderr)
                continue
            fname = f'{iface.name}_{method.name}'
            result.append((iface, method, fname, False))

    for func in reg.functions:
        skip, reason = should_skip_method(reg, func)
        if skip:
            print(f"WARNING: skipping function {func.name}: {reason}",
                  file=sys.stderr)
            continue
        result.append((None, func, func.name, True))

    return result


def method_has_count_output(method):
    """Check if any output param has count_output."""
    for p in method.params:
        if p.output and p.count_output:
            return True
    return False


def method_has_output(method):
    """Check if the method produces any reply data."""
    ret = method.return_type if hasattr(method, 'return_type') else None
    if has_return(ret):
        return True
    for p in method.params:
        if p.output:
            return True
    return False


# ---------------------------------------------------------------------------
# Collect struct dependencies for init functions
# ---------------------------------------------------------------------------

def _collect_init_deps(reg, t, seen, result):
    """Collect types that need init functions, depth-first."""
    if t.name in seen:
        return
    seen.add(t.name)

    for field in t.fields:
        t2 = reg.types.get(field.type_name)
        if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES:
            if t2.is_anonymous:
                # Traverse anonymous type's fields without adding it to result
                for sf in t2.fields:
                    st = reg.types.get(sf.type_name)
                    if st and st.category in ('struct', 'union') \
                            and st.name not in BUILTIN_STRUCT_NAMES \
                            and not st.is_anonymous:
                        _collect_init_deps(reg, st, seen, result)
            else:
                _collect_init_deps(reg, t2, seen, result)

    if not t.is_anonymous:
        result.append(t)


def collect_init_deps(reg, testable_structs, testable_methods):
    """Collect all types that need init functions (including deps)."""
    seen = set()
    result = []

    for (t, member, anon_variant) in testable_structs:
        _collect_init_deps(reg, t, seen, result)

    # Also collect deps from method params
    for (iface, method, fname, is_toplevel) in testable_methods:
        params = method.params if hasattr(method, 'params') else []
        for p in params:
            t2 = reg.types.get(p.type_name)
            if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                _collect_init_deps(reg, t2, seen, result)

    return result


# ---------------------------------------------------------------------------
# Generate npt_test_ids.h
# ---------------------------------------------------------------------------

def generate_test_ids(testable_structs, testable_methods):
    out = StringIO()
    out.write('/* Auto-generated by npt_testgen.py -- do not edit. */\n\n')
    out.write('#ifndef NPT_TEST_IDS_H\n')
    out.write('#define NPT_TEST_IDS_H\n\n')

    out.write('enum npt_test_style {\n')
    out.write('    NPT_STYLE_COUNT_ZERO_PTR_NONNULL = 0,\n')
    out.write('    NPT_STYLE_COUNT_ZERO_PTR_NULL = 1,\n')
    out.write('    NPT_STYLE_COUNT_ONE = 2,\n')
    out.write('    NPT_STYLE_COUNT_NONZERO = 3,\n')
    out.write('    NPT_STYLE_COUNT_OUTPUT_SMALLER = 4,\n')
    out.write('    NPT_STYLE_COUNT_OUTPUT_BIGGER = 5,\n')
    out.write('    NPT_STYLE_COUNT_OUTPUT_INT_MAX = 6,\n')
    out.write('    NPT_STYLE_COUNT_OUTPUT_ERROR_UNSET = 7,\n')
    out.write('    NPT_STYLE_COUNT_OUTPUT_ERROR_ZERO = 8,\n')
    out.write('    NPT_STYLE_COUNT\n')
    out.write('};\n\n')

    out.write('/* Struct test IDs */\n')
    for i, (t, member, anon_variant) in enumerate(testable_structs):
        suffix = f'__{member}' if member else (f'__{anon_variant[1]}' if anon_variant else '')
        out.write(f'#define NPT_TEST_STRUCT_{t.name}{suffix} {i}\n')
    out.write(f'#define NPT_TEST_STRUCT_COUNT {len(testable_structs)}\n\n')

    out.write('/* Method test IDs */\n')
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        out.write(f'#define NPT_TEST_METHOD_{fname} {i}\n')
    out.write(f'#define NPT_TEST_METHOD_COUNT {len(testable_methods)}\n\n')

    out.write('#endif /* NPT_TEST_IDS_H */\n')
    return out.getvalue()


# ---------------------------------------------------------------------------
# Generate test_roundtrip_host.c
# ---------------------------------------------------------------------------

def generate_host(reg, testable_structs, testable_methods, init_types):
    out = StringIO()
    out.write('/* Auto-generated by npt_testgen.py -- do not edit. */\n\n')
    out.write('#include "npt_cs.h"\n')
    out.write('#include "npt_protocol_host.h"\n')
    out.write('#include "npt_test_harness.h"\n')
    out.write('#include "npt_test_ids.h"\n\n')

    out.write('#pragma GCC diagnostic push\n')
    out.write('#pragma GCC diagnostic ignored "-Wunused-variable"\n')
    out.write('#pragma GCC diagnostic ignored "-Wunused-but-set-variable"\n\n')

    # Generate init functions for all needed types
    for t in init_types:
        if t.category == 'union':
            for field in t.fields:
                if field.name:
                    gen_struct_init(out, reg, t, member_name=field.name)
        else:
            gen_struct_init(out, reg, t)

    # Generate anon_variant init functions for structs with anonymous unions
    emitted_anon_inits = set()
    for (t, member, anon_variant) in testable_structs:
        if anon_variant:
            key = f'{t.name}__{anon_variant[1]}'
            if key not in emitted_anon_inits:
                emitted_anon_inits.add(key)
                gen_struct_init(out, reg, t, anon_variant=anon_variant)

    # Generate struct test functions
    for i, (t, member, anon_variant) in enumerate(testable_structs):
        suffix = f'__{member}' if member else (f'__{anon_variant[1]}' if anon_variant else '')
        macro = f'NPT_TEST_STRUCT_{t.name}{suffix}'
        gen_struct_test(out, t.name, suffix, macro)

    # Dispatch: host_test_struct
    out.write('int host_test_struct(int test_id, int style)\n{\n')
    out.write('    switch (test_id) {\n')
    for i, (t, member, anon_variant) in enumerate(testable_structs):
        suffix = f'__{member}' if member else (f'__{anon_variant[1]}' if anon_variant else '')
        out.write(f'    case {i}: return test_struct_{t.name}{suffix}(style);\n')
    out.write('    default: return -1;\n')
    out.write('    }\n}\n\n')

    # Generate host_verify_command functions
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        _gen_host_verify_command(out, reg, iface, method, fname, is_toplevel, i)

    # Dispatch: host_verify_command
    out.write('int host_verify_command(int test_id, int style, '
              'const uint8_t *buf, size_t size)\n{\n')
    out.write('    switch (test_id) {\n')
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        out.write(f'    case {i}: return host_verify_CMD_{fname}(style, buf, size);\n')
    out.write('    default: return -1;\n')
    out.write('    }\n}\n\n')

    # Generate host_encode_reply functions
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        if method_has_output(method):
            _gen_host_encode_reply(out, reg, iface, method, fname, is_toplevel, i)

    # Dispatch: host_encode_reply
    out.write('int host_encode_reply(int test_id, int style, '
              'uint8_t *buf, size_t buf_size, size_t *out_size)\n{\n')
    out.write('    switch (test_id) {\n')
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        if method_has_output(method):
            out.write(f'    case {i}: return host_encode_REPLY_{fname}'
                      f'(style, buf, buf_size, out_size);\n')
    out.write('    default: return -1;\n')
    out.write('    }\n}\n\n')

    out.write('#pragma GCC diagnostic pop\n')
    return out.getvalue()


def _gen_host_verify_command(out, reg, iface, method, fname, is_toplevel, idx):
    """Generate host_verify_CMD_* function that decodes a command and re-encodes
    it for wire comparison."""
    params = method.params if hasattr(method, 'params') else []
    input_params = [p for p in params if p.input]

    out.write(f'static int host_verify_CMD_{fname}(int style, '
              f'const uint8_t *buf, size_t size)\n{{\n')

    # Skip header (interface_id now lives in cmd_type, no trailing UUID).
    out.write(f'    const size_t hdr_size = sizeof(struct npt_command_header);\n')

    out.write(f'    struct npt_cs_decoder dec = npt_test_decoder_init(buf + hdr_size, size - hdr_size);\n')
    out.write(f'    struct npt_command_{fname} args;\n')
    out.write(f'    memset(&args, 0, sizeof(args));\n')
    out.write(f'    npt_decode_{fname}_args_temp(&dec, &args);\n\n')

    # Re-encode
    out.write(f'    /* Re-encode from decoded args */\n')
    out.write(f'    size_t enc_size = size;\n')
    out.write(f'    uint8_t *w2 = (uint8_t *)calloc(1, enc_size ? enc_size : 1);\n')
    out.write(f'    struct npt_cs_encoder enc = npt_test_encoder_init(w2, enc_size);\n\n')

    # Copy command header (no trailing UUID: interface_id is in cmd_type)
    out.write(f'    /* Copy original command header */\n')
    out.write(f'    npt_cs_encoder_write(&enc, sizeof(struct npt_command_header), buf, sizeof(struct npt_command_header));\n')

    # Re-encode each input param (use 'args.' prefix since args is a local struct)
    fields_map = _build_fields_map(params, reg)
    for p in params:
        # Phase-1 refactor: output COM handles now carry a
        # guest-allocated id in the command body, so they belong in
        # the command-side re-encode loop alongside the "real" inputs.
        is_output_com = (p.handle == 'com'
                         and p.indirection == 2
                         and p.output)
        if not p.input and not is_output_com:
            continue
        _gen_reencode_param(out, reg, p, 'args.', fields_map,
                            for_output=False, indent=1)

    out.write(f'\n    size_t w2_actual = npt_test_encoder_written(&enc, w2);\n')
    out.write(f'    int result = npt_wire_compare("CMD_{fname}", buf, size, w2, w2_actual);\n')
    out.write(f'    npt_test_cleanup(&dec);\n')
    out.write(f'    free(w2);\n')
    out.write(f'    return result;\n')
    out.write(f'}}\n\n')


def _gen_host_encode_reply(out, reg, iface, method, fname, is_toplevel, idx):
    """Generate host_encode_REPLY_* function.

    Uses the generated npt_encode_{fname}_reply to produce a wire reply,
    exactly as the real host dispatch code does.
    """
    params = method.params if hasattr(method, 'params') else []
    output_params = [p for p in params if p.output]
    all_params = params
    ret_type = method.return_type if hasattr(method, 'return_type') else None
    _has_ret = has_return(ret_type)
    _is_scalar = is_scalar_return(reg, ret_type)

    out.write(f'static int host_encode_REPLY_{fname}(int style, '
              f'uint8_t *buf, size_t buf_size, size_t *out_size)\n{{\n')

    out.write(f'    uint32_t seed = 0x54321u ^ NPT_TEST_METHOD_{fname} ^ (uint32_t)style;\n')
    out.write(f'    struct npt_command_{fname} args;\n')
    out.write(f'    memset(&args, 0, sizeof(args));\n\n')

    fields_map = _build_fields_map(params, reg)

    # Set up return value
    if _has_ret:
        if ret_type == 'HRESULT':
            out.write(f'    /* Set return value based on style */\n')
            out.write(f'    switch (style) {{\n')
            out.write(f'    case NPT_STYLE_COUNT_OUTPUT_BIGGER:\n')
            out.write(f'    case NPT_STYLE_COUNT_OUTPUT_INT_MAX:\n')
            out.write(f'    case NPT_STYLE_COUNT_OUTPUT_ERROR_UNSET:\n')
            out.write(f'    case NPT_STYLE_COUNT_OUTPUT_ERROR_ZERO:\n')
            out.write(f'        args.ret = (HRESULT)0x80004005; /* E_FAIL */\n')
            out.write(f'        break;\n')
            out.write(f'    default:\n')
            out.write(f'        args.ret = 0; /* S_OK */\n')
            out.write(f'        break;\n')
            out.write(f'    }}\n\n')
        else:
            ret_t = reg.types.get(ret_type)
            if ret_t and ret_t.category in ('struct', 'union') \
                    and ret_t.name not in BUILTIN_STRUCT_NAMES \
                    and not ret_t.is_anonymous:
                if ret_t.category == 'union' and ret_t.fields:
                    umf = ret_t.fields[0]
                    out.write(f'    init_{ret_type}__{umf.name}(({ret_type} *)&args.ret, style, &seed, 1);\n\n')
                else:
                    out.write(f'    init_{ret_type}(({ret_type} *)&args.ret, style, &seed, 1);\n\n')
            elif ret_t and ret_t.category in ('struct', 'union'):
                out.write(f'    npt_test_fill(&args.ret, sizeof(args.ret), &seed);\n\n')
            else:
                out.write(f'    args.ret = ({ret_type})npt_test_rand(&seed);\n\n')

    # Initialize input params (for count fields needed by output)
    _gen_method_param_init(out, reg, params, fields_map, 'args.',
                           output_only=False, for_reply=True)

    # Initialize output params
    _gen_method_param_init(out, reg, params, fields_map, 'args.',
                           output_only=True, for_reply=True)

    # Handle count_output styles
    _gen_count_output_styles(out, reg, params, fields_map)

    # Use the generated npt_encode_{fname}_reply (host-side) which takes
    # a pointer to the npt_command_* struct.  Encode directly into buf
    # (caller provides a 1MB buffer) and report actual bytes written.
    out.write(f'    struct npt_cs_encoder enc = npt_test_encoder_init(buf, buf_size);\n')
    out.write(f'    npt_encode_{fname}_reply(&enc, &args);\n')
    out.write(f'    *out_size = npt_test_encoder_written(&enc, buf);\n')
    out.write(f'    npt_test_alloc_free_all();\n')
    out.write(f'    return 0;\n')
    out.write(f'}}\n\n')




def _gen_method_param_init(out, reg, params, fields_map, prefix,
                           output_only=False, for_reply=False):
    """Generate initialization code for method params."""
    count_map = _find_count_fields(params, reg)

    # Two sub-passes: count fields first (so dependent fields see the value),
    # then all other fields.
    def _should_process(p):
        if output_only and not p.output:
            return False
        if not output_only and not p.input:
            return False
        if output_only and p.input and p.output:
            return False
        if p.name is None:
            return False
        return True

    # Sub-pass 1: count fields only
    for p in params:
        if not _should_process(p):
            continue
        if p.name not in count_map:
            continue
        if p.indirection >= 1:
            out.write(f'    {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
            if p.const:
                deref = f'*({p.type_name} *)'
            else:
                deref = '*'
        else:
            deref = ''
        out.write(f'    switch (style) {{\n')
        out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NONNULL:\n')
        out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NULL:\n')
        out.write(f'        {deref}{prefix}{p.name} = 0;\n')
        out.write(f'        break;\n')
        out.write(f'    case NPT_STYLE_COUNT_ONE:\n')
        out.write(f'        {deref}{prefix}{p.name} = 1;\n')
        out.write(f'        break;\n')
        out.write(f'    case NPT_STYLE_COUNT_NONZERO:\n')
        out.write(f'    default:\n')
        out.write(f'        {deref}{prefix}{p.name} = 5;\n')
        out.write(f'        break;\n')
        out.write(f'    }}\n')

    # Sub-pass 2: all other fields
    for p in params:
        if not _should_process(p):
            continue
        if p.name in count_map:
            continue  # already handled in sub-pass 1

        cls = classify_field(reg, p)

        if cls == 'NON_SERIALIZABLE':
            if p.optional:
                out.write(f'    {prefix}{p.name} = NULL;\n')
            continue

        if cls in ('COM_HANDLE', 'INTERFACE_REF'):
            if p.output and not p.input:
                # Output COM handle: allocate storage
                if p.indirection == 2:
                    out.write(f'    {prefix}{p.name} = ({_param_cast_type(p)})npt_test_alloc(sizeof(void *));\n')
                    out.write(f'    *{prefix}{p.name} = npt_test_handle_create(&seed);\n')
                else:
                    out.write(f'    {prefix}{p.name} = npt_test_handle_create(&seed);\n')
            elif p.input:
                out.write(f'    {prefix}{p.name} = '
                          f'({_param_cast_type(p)})npt_test_handle_create(&seed);\n')
            continue

        if cls == 'WIN32_HANDLE':
            if p.indirection >= 1 and p.output:
                out.write(f'    {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
                out.write(f'    *{prefix}{p.name} = ({p.type_name})(uintptr_t)npt_test_handle_create(&seed);\n')
            elif p.indirection >= 1:
                out.write(f'    {prefix}{p.name} = '
                          f'npt_test_handle_create(&seed);\n')
            else:
                out.write(f'    {prefix}{p.name} = '
                          f'({p.type_name})(uintptr_t)npt_test_handle_create(&seed);\n')
            continue

        if cls == 'COM_HANDLE_ARRAY':
            cnt = get_count_expr(p, prefix, fields_map)
            if cnt:
                out.write(f'    if ({cnt} > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof(void *) * {cnt});\n')
                out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                out.write(f'            {prefix}{p.name}[_i] = npt_test_handle_create(&seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }}\n')
            continue

        if cls == 'STRING':
            out.write(f'    {prefix}{p.name} = ({p.type_name} *)npt_test_string(&seed, 8);\n')
            continue

        if cls == 'WSTRING':
            out.write(f'    {prefix}{p.name} = ({p.type_name} *)npt_test_wstring(&seed, 8);\n')
            continue

        if cls == 'BLOB':
            cnt = get_count_expr(p, prefix, fields_map)
            if cnt:
                out.write(f'    {{ size_t _cnt = npt_test_clamp_count({cnt}, 1);\n')
                out.write(f'    if (_cnt > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(_cnt);\n')
                out.write(f'        npt_test_fill((void *){prefix}{p.name}, _cnt, &seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }} }}\n')
            continue

        if cls == 'STRING_ARRAY':
            cnt = get_count_expr(p, prefix, fields_map)
            is_wide = _is_wide_string_field(reg, p)
            str_fn = 'npt_test_wstring' if is_wide else 'npt_test_string'
            if cnt:
                out.write(f'    {{ size_t _cnt = npt_test_clamp_count({cnt}, sizeof(void *));\n')
                out.write(f'    if (_cnt > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof(void *) * _cnt);\n')
                out.write(f'        for (uint32_t _i = 0; _i < (uint32_t)_cnt; _i++)\n')
                out.write(f'            {prefix}{p.name}[_i] = ({p.type_name} *){str_fn}(&seed, 6);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }} }}\n')
            continue

        if cls in ('FIXED_ARRAY', 'COUNTED_ARRAY'):
            cnt = get_count_expr(p, prefix, fields_map)
            if cnt:
                base = reg.resolve_alias_chain(p.type_name)
                is_prim = base in PRIMITIVE_NAMES or reg.is_enum(p)
                out.write(f'    {{ size_t _cnt = npt_test_clamp_count({cnt}, sizeof({p.type_name}));\n')
                out.write(f'    if (_cnt > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}) * _cnt);\n')
                if is_prim:
                    out.write(f'        npt_test_fill((void *){prefix}{p.name}, '
                              f'sizeof({p.type_name}) * _cnt, &seed);\n')
                else:
                    t2 = reg.types.get(p.type_name)
                    if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                        if t2.category == 'union' and t2.fields:
                            mf = t2.fields[0]
                            out.write(f'        for (uint32_t _i = 0; _i < (uint32_t)_cnt; _i++)\n')
                            out.write(f'            init_{p.type_name}__{mf.name}'
                                      f'(&(({p.type_name} *){prefix}{p.name})[_i], style, &seed, 1);\n')
                        else:
                            out.write(f'        for (uint32_t _i = 0; _i < (uint32_t)_cnt; _i++)\n')
                            out.write(f'            init_{p.type_name}'
                                      f'(&(({p.type_name} *){prefix}{p.name})[_i], style, &seed, 1);\n')
                    else:
                        out.write(f'        npt_test_fill((void *){prefix}{p.name}, '
                                  f'sizeof({p.type_name}) * _cnt, &seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }} }}\n')
            continue

        if cls == 'SIMPLE_POINTER':
            if p.optional:
                out.write(f'    if (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) {{\n')
                out.write(f'        {prefix}{p.name} = NULL;\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
                t2 = reg.types.get(p.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'        init_{p.type_name}__{mf.name}'
                                  f'(({p.type_name} *){prefix}{p.name}, style, &seed, 1);\n')
                    else:
                        out.write(f'        init_{p.type_name}'
                                  f'(({p.type_name} *){prefix}{p.name}, style, &seed, 1);\n')
                else:
                    out.write(f'        npt_test_fill((void *){prefix}{p.name}, '
                              f'sizeof({p.type_name}), &seed);\n')
                out.write(f'    }}\n')
            else:
                out.write(f'    {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
                t2 = reg.types.get(p.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'    init_{p.type_name}__{mf.name}'
                                  f'(({p.type_name} *){prefix}{p.name}, style, &seed, 1);\n')
                    else:
                        out.write(f'    init_{p.type_name}'
                                  f'(({p.type_name} *){prefix}{p.name}, style, &seed, 1);\n')
                else:
                    out.write(f'    npt_test_fill((void *){prefix}{p.name}, '
                              f'sizeof({p.type_name}), &seed);\n')
            continue

        if cls == 'SCALAR':
            if p.name not in count_map:
                t2 = reg.types.get(p.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'    init_{p.type_name}__{mf.name}'
                                  f'(&{prefix}{p.name}, style, &seed, 1);\n')
                    else:
                        out.write(f'    init_{p.type_name}'
                                  f'(&{prefix}{p.name}, style, &seed, 1);\n')
                elif t2 and t2.category in ('struct', 'union'):
                    # Builtin or anonymous struct: fill with random data
                    out.write(f'    npt_test_fill(&{prefix}{p.name}, sizeof({p.type_name}), &seed);\n')
                else:
                    out.write(f'    {prefix}{p.name} = ({p.type_name})npt_test_rand(&seed);\n')
            continue

        if cls == 'BITFIELD':
            mask = (1 << p.bitwidth) - 1
            out.write(f'    {prefix}{p.name} = npt_test_rand(&seed) & 0x{mask:x}u;\n')
            continue


def _param_cast_type(p):
    """Get the C cast type for a method param handle."""
    parts = []
    parts.append(p.type_name if p.type_name else 'void')
    result = ' '.join(parts)
    indirection = p.indirection
    if indirection == 0 and _is_fixed_array(p):
        indirection = 1
    result += ' ' + '*' * indirection
    return result.strip()


def _gen_count_output_styles(out, reg, params, fields_map):
    """Generate count_output style adjustments."""
    for p in params:
        if not p.output or not p.count_output:
            continue
        co = p.count_output
        deref = fields_map.get(co, -1)
        if deref < 0:
            co_expr = co
        else:
            co_expr = f'{"*" * deref}args.{co}'

        # The count_output field is a pointer that was allocated; dereference
        out.write(f'    /* count_output adjustments for {p.name} */\n')
        out.write(f'    switch (style) {{\n')
        out.write(f'    case NPT_STYLE_COUNT_OUTPUT_SMALLER:\n')
        out.write(f'        if (args.{co}) *args.{co} = 1;\n')
        out.write(f'        break;\n')
        out.write(f'    case NPT_STYLE_COUNT_OUTPUT_BIGGER:\n')
        out.write(f'        if (args.{co}) *args.{co} = 100;\n')
        out.write(f'        break;\n')
        out.write(f'    case NPT_STYLE_COUNT_OUTPUT_INT_MAX:\n')
        out.write(f'        if (args.{co}) *args.{co} = INT_MAX;\n')
        out.write(f'        break;\n')
        out.write(f'    case NPT_STYLE_COUNT_OUTPUT_ERROR_ZERO:\n')
        out.write(f'        if (args.{co}) *args.{co} = 0;\n')
        out.write(f'        break;\n')
        out.write(f'    default:\n')
        # For success styles: set count_output to the input count (capacity)
        cnt = get_count_expr(p, 'args.', fields_map)
        if cnt:
            out.write(f'        if (args.{co}) *args.{co} = {cnt};\n')
        out.write(f'        break;\n')
        out.write(f'    }}\n')


def _gen_reencode_param(out, reg, field, prefix, fields_map, for_output=False,
                        indent=1):
    """Generate re-encode code for a single param."""
    ind = '    ' * indent
    acc = f'{prefix}{field.name}'

    cls = classify_field(reg, field)

    if cls == 'NON_SERIALIZABLE':
        if field.optional:
            out.write(f'{ind}/* {field.name}: non-serializable, skip */\n')
        return

    if cls == 'BITFIELD':
        out.write(f'{ind}{{ uint32_t _tmp = {acc};\n')
        out.write(f'{ind}  npt_encode_uint32_t(&enc, &_tmp); }}\n')
        return

    if cls == 'ANONYMOUS_INLINE':
        t2 = reg.types.get(field.type_name)
        if t2:
            for inner in t2.fields:
                _gen_reencode_param(out, reg, inner, prefix, fields_map,
                                    for_output, indent)
        return

    if cls in ('COM_HANDLE', 'INTERFACE_REF'):
        if field.indirection == 2 and field.output:
            # Output COM handle (double pointer).
            #
            # Phase-1 refactor: on the COMMAND side (for_output=False)
            # we emit a guest-allocated uint64 id in the body.  On the
            # REPLY side (for_output=True) we emit nothing -- the host
            # registered the id post-dispatch and the guest already
            # knows it.  The test harness must mirror the wire layout.
            cnt = get_count_expr(field, prefix, fields_map)
            if for_output:
                # Reply side: no data on the wire for output COM handles.
                return
            # Command side: re-encode the guest-allocated id(s) that
            # the decoder read into the args struct's shadow fields.
            # Mirroring the decoded value means the re-encode produces
            # identical bytes to the original encode regardless of
            # what npt_com_allocate_next_id returned on the first pass.
            if cnt:
                out.write(f'{ind}if ({acc}) {{\n')
                out.write(f'{ind}    const uint64_t _n = '
                          f'{prefix}_guest_id_count_{field.name};\n')
                out.write(f'{ind}    npt_encode_array_count(&enc, _n);\n')
                out.write(f'{ind}    for (uint32_t _i = 0; _i < (uint32_t)_n; '
                          f'_i++) {{\n')
                out.write(f'{ind}        const uint64_t _gid = '
                          f'{prefix}_guest_ids_{field.name}'
                          f'[_i];\n')
                out.write(f'{ind}        npt_encode_uint64_t(&enc, &_gid);\n')
                out.write(f'{ind}    }}\n')
                out.write(f'{ind}}} else {{\n')
                out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
                out.write(f'{ind}}}\n')
            else:
                out.write(f'{ind}{{\n')
                out.write(f'{ind}    const uint64_t _gid = '
                          f'{prefix}_guest_id_{field.name};\n')
                out.write(f'{ind}    npt_encode_uint64_t(&enc, &_gid);\n')
                out.write(f'{ind}}}\n')
        elif field.indirection >= 1:
            out.write(f'{ind}npt_encode_com_handle(&enc, npt_object_get_id({acc}));\n')
        else:
            out.write(f'{ind}npt_encode_com_handle(&enc, npt_object_get_id((const void *)(uintptr_t){acc}));\n')
        return

    if cls == 'WIN32_HANDLE':
        if field.indirection >= 1:
            out.write(f'{ind}npt_encode_win32_handle(&enc, npt_win32_handle_get_id((const void *)(uintptr_t)*{acc}));\n')
        else:
            out.write(f'{ind}npt_encode_win32_handle(&enc, npt_win32_handle_get_id((const void *)(uintptr_t){acc}));\n')
        return

    if cls == 'COM_HANDLE_ARRAY':
        cnt = get_count_expr(field, prefix, fields_map)
        if for_output and field.output and field.indirection == 2:
            # Phase-1 refactor: output COM handle arrays carry their
            # guest-allocated ids in the COMMAND body, not the reply.
            # The reply-side re-encoder emits nothing for them.
            return
        if not for_output and field.output and field.indirection == 2:
            # Command-side re-encode of an output COM handle array:
            # read the decoded guest ids back out of the shadow field
            # and encode them so buf vs w2 match byte-for-byte.
            if cnt:
                out.write(f'{ind}if ({acc}) {{\n')
                out.write(f'{ind}    const uint64_t _n = '
                          f'{prefix}_guest_id_count_{field.name};\n')
                out.write(f'{ind}    npt_encode_array_count(&enc, _n);\n')
                out.write(f'{ind}    for (uint32_t _i = 0; _i < (uint32_t)_n; '
                          f'_i++) {{\n')
                out.write(f'{ind}        const uint64_t _gid = '
                          f'{prefix}_guest_ids_{field.name}[_i];\n')
                out.write(f'{ind}        npt_encode_uint64_t(&enc, &_gid);\n')
                out.write(f'{ind}    }}\n')
                out.write(f'{ind}}} else {{\n')
                out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
                out.write(f'{ind}}}\n')
            return
        if cnt:
            out.write(f'{ind}if ({acc}) {{\n')
            out.write(f'{ind}    npt_encode_array_count(&enc, {cnt});\n')
            if for_output:
                out.write(f'{ind}    for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++) {{\n')
                out.write(f'{ind}        npt_object_id _out_id = {acc}[_i]\n')
                out.write(f'{ind}            ? npt_object_get_id({acc}[_i]) : 0;\n')
                out.write(f'{ind}        npt_encode_uint64_t(&enc, &_out_id);\n')
                out.write(f'{ind}    }}\n')
            else:
                out.write(f'{ind}    for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                out.write(f'{ind}        npt_encode_com_handle(&enc, npt_object_get_id({acc}[_i]));\n')
            out.write(f'{ind}}} else {{\n')
            out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
            out.write(f'{ind}}}\n')
        return

    if cls == 'SCALAR':
        t2 = reg.types.get(field.type_name)
        if t2 and t2.is_anonymous:
            out.write(f'{ind}npt_encode_{field.type_name}(&enc, (const {field.type_name} *)&{acc});\n')
        else:
            out.write(f'{ind}npt_encode_{field.type_name}(&enc, &{acc});\n')
        return

    if cls == 'FIXED_ARRAY':
        cnt = get_count_expr(field, prefix, fields_map)
        base = reg.resolve_alias_chain(field.type_name)
        if base in PRIMITIVE_NAMES or reg.is_enum(field):
            out.write(f'{ind}npt_encode_array_count(&enc, {cnt});\n')
            out.write(f'{ind}npt_encode_{field.type_name}_array(&enc, (const {field.type_name} *){acc}, {cnt});\n')
        else:
            out.write(f'{ind}npt_encode_array_count(&enc, {cnt});\n')
            out.write(f'{ind}for (uint32_t _i = 0; _i < (uint32_t)({cnt}); _i++)\n')
            out.write(f'{ind}    npt_encode_{field.type_name}(&enc, &{acc}[_i]);\n')
        return

    if cls == 'STRING':
        out.write(f'{ind}if ({acc}) {{\n')
        out.write(f'{ind}    const size_t _s = strlen((const char *){acc}) + 1;\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, _s);\n')
        out.write(f'{ind}    npt_encode_blob_array(&enc, {acc}, _s);\n')
        out.write(f'{ind}}} else {{\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
        out.write(f'{ind}}}\n')
        return

    if cls == 'WSTRING':
        out.write(f'{ind}if ({acc}) {{\n')
        out.write(f'{ind}    const size_t _s = (npt_wcslen((const WCHAR *){acc}) + 1) * sizeof(WCHAR);\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, _s);\n')
        out.write(f'{ind}    npt_encode_blob_array(&enc, {acc}, _s);\n')
        out.write(f'{ind}}} else {{\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
        out.write(f'{ind}}}\n')
        return

    if cls == 'STRING_ARRAY':
        cnt = get_count_expr(field, prefix, fields_map)
        is_wide = _is_wide_string_field(reg, field)
        if is_wide:
            strlen_fn = f'(npt_wcslen((const WCHAR *){acc}[_i]) + 1) * sizeof(WCHAR)'
        else:
            strlen_fn = f'strlen((const char *){acc}[_i]) + 1'
        out.write(f'{ind}if ({acc}) {{\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, {cnt});\n')
        out.write(f'{ind}    for (uint64_t _i = 0; _i < (uint64_t){cnt}; _i++) {{\n')
        out.write(f'{ind}        const size_t _slen = {acc}[_i] ? {strlen_fn} : 0;\n')
        out.write(f'{ind}        npt_encode_array_count(&enc, _slen);\n')
        out.write(f'{ind}        npt_encode_blob_array(&enc, {acc}[_i], _slen);\n')
        out.write(f'{ind}    }}\n')
        out.write(f'{ind}}} else {{\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
        out.write(f'{ind}}}\n')
        return

    if cls == 'BLOB':
        if for_output:
            cnt = get_output_count_expr(field, prefix, fields_map)
        else:
            cnt = get_count_expr(field, prefix, fields_map)
        if cnt is None:
            cnt = '0'
        out.write(f'{ind}if ({acc}) {{\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, {cnt});\n')
        out.write(f'{ind}    npt_encode_blob_array(&enc, {acc}, {cnt});\n')
        out.write(f'{ind}}} else {{\n')
        out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
        out.write(f'{ind}}}\n')
        return

    if cls == 'COUNTED_ARRAY':
        if for_output:
            cnt = get_output_count_expr(field, prefix, fields_map)
        else:
            cnt = get_count_expr(field, prefix, fields_map)
        if cnt is None:
            return
        base = reg.resolve_alias_chain(field.type_name)
        if base in PRIMITIVE_NAMES or reg.is_enum(field):
            out.write(f'{ind}if ({acc}) {{\n')
            out.write(f'{ind}    npt_encode_array_count(&enc, {cnt});\n')
            out.write(f'{ind}    npt_encode_{field.type_name}_array(&enc, {acc}, {cnt});\n')
            out.write(f'{ind}}} else {{\n')
            out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
            out.write(f'{ind}}}\n')
        else:
            out.write(f'{ind}if ({acc}) {{\n')
            out.write(f'{ind}    npt_encode_array_count(&enc, {cnt});\n')
            out.write(f'{ind}    for (uint32_t _i = 0; _i < (uint32_t)({cnt}); _i++)\n')
            out.write(f'{ind}        npt_encode_{field.type_name}(&enc, &{acc}[_i]);\n')
            out.write(f'{ind}}} else {{\n')
            out.write(f'{ind}    npt_encode_array_count(&enc, 0);\n')
            out.write(f'{ind}}}\n')
        return

    if cls == 'SIMPLE_POINTER':
        out.write(f'{ind}if (npt_encode_simple_pointer(&enc, {acc}))\n')
        out.write(f'{ind}    npt_encode_{field.type_name}(&enc, {acc});\n')
        return

    # UNSIZED optional
    if field.optional:
        out.write(f'{ind}npt_encode_array_count(&enc, 0); /* {field.name}: unsized optional */\n')


# ---------------------------------------------------------------------------
# Generate test_roundtrip_guest.c
# ---------------------------------------------------------------------------

def generate_guest(reg, testable_methods, init_types):
    out = StringIO()
    out.write('/* Auto-generated by npt_testgen.py -- do not edit. */\n\n')
    out.write('#include "npt_cs.h"\n')
    out.write('#include "npt_protocol_guest.h"\n')
    out.write('#include "npt_test_harness.h"\n')
    out.write('#include "npt_test_ids.h"\n\n')

    out.write('#pragma GCC diagnostic push\n')
    out.write('#pragma GCC diagnostic ignored "-Wunused-variable"\n')
    out.write('#pragma GCC diagnostic ignored "-Wunused-but-set-variable"\n\n')

    # Init functions (same as host, but for guest side we might need them too)
    for t in init_types:
        if t.category == 'union':
            for field in t.fields:
                if field.name:
                    gen_struct_init(out, reg, t, member_name=field.name)
        else:
            gen_struct_init(out, reg, t)

    # Generate guest_encode_command functions
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        _gen_guest_encode_command(out, reg, iface, method, fname, is_toplevel, i)

    # Dispatch: guest_encode_command
    out.write('int guest_encode_command(int test_id, int style, '
              'uint8_t *buf, size_t buf_size, size_t *out_size)\n{\n')
    out.write('    switch (test_id) {\n')
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        out.write(f'    case {i}: return guest_encode_CMD_{fname}'
                  f'(style, buf, buf_size, out_size);\n')
    out.write('    default: return -1;\n')
    out.write('    }\n}\n\n')

    # Generate guest_verify_reply functions
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        if method_has_output(method):
            _gen_guest_verify_reply(out, reg, iface, method, fname, is_toplevel, i)

    # Dispatch: guest_verify_reply
    out.write('int guest_verify_reply(int test_id, int style, '
              'const uint8_t *buf, size_t size)\n{\n')
    out.write('    switch (test_id) {\n')
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        if method_has_output(method):
            out.write(f'    case {i}: return guest_verify_REPLY_{fname}'
                      f'(style, buf, size);\n')
    out.write('    default: return -1;\n')
    out.write('    }\n}\n\n')

    out.write('#pragma GCC diagnostic pop\n')
    return out.getvalue()


def _gen_guest_encode_command(out, reg, iface, method, fname, is_toplevel, idx):
    """Generate guest_encode_CMD_* function."""
    params = method.params if hasattr(method, 'params') else []
    input_params = [p for p in params if p.input]

    out.write(f'static int guest_encode_CMD_{fname}(int style, '
              f'uint8_t *buf, size_t buf_size, size_t *out_size)\n{{\n')
    out.write(f'    uint32_t seed = 0x12345u ^ NPT_TEST_METHOD_{fname} ^ (uint32_t)style;\n')

    fields_map = _build_fields_map(params, reg)

    # Declare and initialize all params
    for p in params:
        ctype = _c_type_for_param(p)
        out.write(f'    {ctype} p_{p.name} = {_zero_init(reg, p)};\n')

    out.write('\n')

    # Initialize params
    _gen_method_param_init_guest(out, reg, params, fields_map, 'p_')

    # Compute size and encode
    all_param_names = ', '.join(f'p_{p.name}' for p in params)
    if not params:
        all_param_names = ''

    out.write(f'\n    size_t cmd_size = npt_sizeof_{fname}({all_param_names});\n')
    out.write(f'    if (cmd_size > buf_size) return -1;\n')
    out.write(f'    struct npt_cs_encoder enc = npt_test_encoder_init(buf, cmd_size);\n')

    if is_toplevel:
        encode_args = f'&enc, NPT_CMD_FLAG_REPLY'
    else:
        encode_args = f'&enc, NPT_CMD_FLAG_REPLY, 0xDEAD'

    if params:
        encode_args += ', ' + ', '.join(f'p_{p.name}' for p in params)

    out.write(f'    npt_encode_{fname}({encode_args});\n')
    out.write(f'    *out_size = npt_test_encoder_written(&enc, buf);\n')
    out.write(f'    npt_test_alloc_free_all();\n')
    out.write(f'    return 0;\n')
    out.write(f'}}\n\n')


def _gen_guest_verify_reply(out, reg, iface, method, fname, is_toplevel, idx):
    """Generate guest_verify_REPLY_* function that decodes a reply and re-encodes it."""
    params = method.params if hasattr(method, 'params') else []
    output_params = [p for p in params if p.output]
    ret_type = method.return_type if hasattr(method, 'return_type') else None
    _has_ret = has_return(ret_type)
    _is_scalar = is_scalar_return(reg, ret_type)

    out.write(f'static int guest_verify_REPLY_{fname}(int style, '
              f'const uint8_t *buf, size_t size)\n{{\n')

    fields_map = _build_fields_map(params, reg)

    # Find count fields that are referenced by output params
    output_names = {p.name for p in output_params}
    count_map_all = _find_count_fields(params, reg)
    input_count_names = set()
    for cname, deps in count_map_all.items():
        if cname in output_names:
            continue  # already declared as output
        # Check if any dependent field is an output param
        if any(d.output for d in deps):
            input_count_names.add(cname)

    # Declare and initialize input-only count fields needed by output params
    for p in params:
        if p.name in input_count_names and p.input and not p.output:
            ctype = _c_type_for_param(p)
            out.write(f'    {ctype} p_{p.name} = {_zero_init(reg, p)};\n')
            if p.indirection >= 1:
                out.write(f'    {p.type_name} _cnt_backing_{p.name} = 0;\n')
                out.write(f'    p_{p.name} = &_cnt_backing_{p.name};\n')
                if p.const:
                    deref = f'*({p.type_name} *)'
                else:
                    deref = '*'
            else:
                deref = ''
            out.write(f'    switch (style) {{\n')
            out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NONNULL:\n')
            out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NULL:\n')
            out.write(f'        {deref}p_{p.name} = 0; break;\n')
            out.write(f'    case NPT_STYLE_COUNT_ONE:\n')
            out.write(f'        {deref}p_{p.name} = 1; break;\n')
            out.write(f'    case NPT_STYLE_COUNT_NONZERO: default:\n')
            out.write(f'        {deref}p_{p.name} = 5; break;\n')
            out.write(f'    }}\n')

    # Allocate storage for output params
    for p in output_params:
        ctype = _c_type_for_param(p)
        out.write(f'    {ctype} p_{p.name} = {_zero_init(reg, p)};\n')

        # Allocate backing storage for output pointers
        cls = classify_field(reg, p)
        if cls == 'SIMPLE_POINTER' or (cls == 'SCALAR' and p.indirection == 1):
            if p.indirection >= 2:
                const_prefix = 'const ' if p.const else ''
                backing_type = f'{const_prefix}{p.type_name} *'
                out.write(f'    {backing_type}_backing_{p.name} = NULL;\n')
                out.write(f'    p_{p.name} = &_backing_{p.name};\n')
            elif p.optional:
                # Optional output: match host init (NULL for COUNT_ZERO_PTR_NULL).
                # Exception: count fields are always allocated by the host.
                count_map = _find_count_fields(params, reg)
                is_count = p.name in count_map
                out.write(f'    {p.type_name} _backing_{p.name};\n')
                out.write(f'    memset(&_backing_{p.name}, 0, sizeof(_backing_{p.name}));\n')
                if is_count:
                    # Count fields always have backing
                    out.write(f'    p_{p.name} = &_backing_{p.name};\n')
                else:
                    out.write(f'    if (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) {{\n')
                    out.write(f'        p_{p.name} = NULL;\n')
                    out.write(f'    }} else {{\n')
                    out.write(f'        p_{p.name} = &_backing_{p.name};\n')
                    out.write(f'    }}\n')
            else:
                out.write(f'    {p.type_name} _backing_{p.name};\n')
                out.write(f'    memset(&_backing_{p.name}, 0, sizeof(_backing_{p.name}));\n')
                out.write(f'    p_{p.name} = &_backing_{p.name};\n')
        elif cls in ('COM_HANDLE', 'INTERFACE_REF') and p.indirection == 2:
            out.write(f'    void *_backing_{p.name} = NULL;\n')
            out.write(f'    p_{p.name} = ({_param_cast_type(p)})&_backing_{p.name};\n')
        elif cls == 'WIN32_HANDLE' and p.indirection >= 1 and p.output:
            out.write(f'    {p.type_name} _backing_{p.name} = 0;\n')
            out.write(f'    p_{p.name} = &_backing_{p.name};\n')
        elif cls in ('COM_HANDLE_ARRAY', 'BLOB', 'COUNTED_ARRAY',
                     'STRING_ARRAY', 'FIXED_ARRAY'):
            # For output arrays, allocate storage for the decode to fill.
            # Try to use the count expression (from input count fields).
            # If the count field is another output param (not yet
            # available), fall back to a generous allocation from the
            # wire size.
            cnt = get_count_expr(p, 'p_', fields_map)
            # Check if the count expression references output params
            # that may not be declared yet (they are declared in the
            # same output-params loop, possibly after the current one).
            cnt_valid = cnt is not None
            if cnt_valid and cnt != '0':
                for term in (cnt.split(' * ') if ' * ' in cnt else [cnt]):
                    term = term.strip().lstrip('*')
                    # Strip prefix
                    if term.startswith('p_'):
                        field_name = term[2:]
                    else:
                        field_name = term
                    # Skip numeric and sizeof() terms
                    if field_name.isdigit() or field_name.startswith('sizeof('):
                        continue
                    # If this field is in the output params list, its
                    # variable may not yet be declared at this point.
                    if field_name in output_names:
                        cnt_valid = False
                        break

            if cnt_valid and cnt != '0':
                if cls == 'BLOB':
                    alloc_size = cnt
                elif cls in ('COM_HANDLE_ARRAY', 'STRING_ARRAY'):
                    alloc_size = f'sizeof(void *) * {cnt}'
                else:
                    alloc_size = f'sizeof({p.type_name}) * {cnt}'
                out.write(f'    if ({cnt} > 0) {{\n')
                out.write(f'        p_{p.name} = npt_test_alloc({alloc_size});\n')
                out.write(f'    }} else {{\n')
                out.write(f'        p_{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }}\n')
            else:
                # Count references output params.  Determine whether the
                # count param comes before or after this array in the
                # output params list to match the host init order.
                count_after = _count_field_after_array(p, output_params)
                if count_after:
                    # Count param comes after → host used the initial
                    # (style-based) count for allocation.  Replicate.
                    if cls == 'BLOB':
                        alloc_size = f'_alloc_cnt_{p.name}'
                    elif cls in ('COM_HANDLE_ARRAY', 'STRING_ARRAY'):
                        alloc_size = f'sizeof(void *) * _alloc_cnt_{p.name}'
                    else:
                        alloc_size = f'sizeof({p.type_name}) * _alloc_cnt_{p.name}'
                    out.write(f'    {{ {count_after.type_name} _alloc_cnt_{p.name} = 0;\n')
                    out.write(f'    switch (style) {{\n')
                    out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NONNULL:\n')
                    out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NULL:\n')
                    out.write(f'        _alloc_cnt_{p.name} = 0; break;\n')
                    out.write(f'    case NPT_STYLE_COUNT_ONE:\n')
                    out.write(f'        _alloc_cnt_{p.name} = 1; break;\n')
                    out.write(f'    case NPT_STYLE_COUNT_NONZERO: default:\n')
                    out.write(f'        _alloc_cnt_{p.name} = 5; break;\n')
                    out.write(f'    }}\n')
                    out.write(f'    if (_alloc_cnt_{p.name} > 0) {{\n')
                    out.write(f'        p_{p.name} = npt_test_alloc({alloc_size});\n')
                    out.write(f'    }} else {{\n')
                    out.write(f'        p_{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                    out.write(f'    }} }}\n')
                else:
                    # Count param comes before (already re-set) →
                    # allocate from wire size (generous).
                    out.write(f'    if (size > 0)\n')
                    out.write(f'        p_{p.name} = npt_test_alloc(size);\n')

    if _has_ret:
        ret_t = reg.types.get(ret_type)
        if ret_t and ret_t.category in ('struct', 'union'):
            out.write(f'    {ret_type} ret_val = {{0}};\n')
        else:
            out.write(f'    {ret_type} ret_val = 0;\n')

    # Decode reply
    out.write(f'\n    struct npt_cs_decoder dec = npt_test_decoder_init(buf, size);\n')

    decode_args = '&dec'
    for p in output_params:
        decode_args += f', p_{p.name}'
    if _has_ret:
        decode_args += ', &ret_val'
    out.write(f'    npt_decode_{fname}_reply({decode_args});\n\n')

    # Re-encode for comparison
    out.write(f'    uint8_t *w2 = (uint8_t *)calloc(1, size ? size : 1);\n')
    out.write(f'    struct npt_cs_encoder enc = npt_test_encoder_init(w2, size);\n\n')

    # Write reply header
    out.write(f'    struct npt_reply_header _reply;\n')
    if is_toplevel:
        func_obj = method  # It's actually a function object
        out.write(f'    _reply.cmd_type = NPT_CMD_TYPE_TOPLEVEL({func_obj.group}, {func_obj.id});\n')
    else:
        out.write(f'    _reply.cmd_type = NPT_CMD_TYPE(255, NPT_IFACE_ID_{iface.name}, '
                  f'NPT_METHOD_{fname});\n')

    if _is_scalar:
        out.write(f'    _reply.cmd_return = (uint32_t)ret_val;\n')
    else:
        out.write(f'    _reply.cmd_return = 0;\n')
    out.write(f'    npt_cs_encoder_write(&enc, sizeof(_reply), &_reply, sizeof(_reply));\n')

    # Non-scalar return
    if _has_ret and not _is_scalar:
        out.write(f'    npt_encode_{ret_type}(&enc, &ret_val);\n')

    # Re-encode output params
    for p in output_params:
        if p.count_output and ret_type == 'HRESULT':
            out.write(f'    if ((HRESULT)ret_val >= 0) {{\n')
            _gen_reencode_reply_param(out, reg, p, 'p_', fields_map, indent=2)
            out.write(f'    }} else {{\n')
            out.write(f'        npt_encode_array_count(&enc, 0);\n')
            out.write(f'    }}\n')
        else:
            _gen_reencode_reply_param(out, reg, p, 'p_', fields_map, indent=1)

    out.write(f'\n    size_t w2_actual = npt_test_encoder_written(&enc, w2);\n')
    out.write(f'    int result = npt_wire_compare("REPLY_{fname}", buf, size, w2, w2_actual);\n')
    out.write(f'    npt_test_cleanup(&dec);\n')
    out.write(f'    free(w2);\n')
    out.write(f'    return result;\n')
    out.write(f'}}\n\n')


def _gen_reencode_reply_param(out, reg, field, prefix, fields_map, indent=1):
    """Re-encode an output param for reply verification."""
    # Same logic as _gen_reencode_param but with for_output=True
    _gen_reencode_param(out, reg, field, prefix, fields_map,
                        for_output=True, indent=indent)


def _c_type_for_param(p):
    """Get the C type declaration for a parameter variable."""
    parts = []
    if p.const:
        parts.append('const')
    parts.append(p.type_name if p.type_name else 'void')
    result = ' '.join(parts)
    indirection = p.indirection
    # Fixed-size arrays at indirection 0 become pointers in command struct
    if indirection == 0 and _is_fixed_array(p):
        indirection = 1
    if indirection > 0:
        result += ' ' + '*' * indirection
    return result


def _zero_init(reg, p):
    """Get zero initializer for a param type."""
    if p.indirection > 0 or (p.indirection == 0 and _is_fixed_array(p)):
        return 'NULL'
    # Use {0} for struct/union types, 0 for scalars
    t = reg.types.get(p.type_name)
    if t and t.category in ('struct', 'union'):
        return '{0}'
    return '0'


def _gen_method_param_init_guest(out, reg, params, fields_map, prefix):
    """Generate initialization code for method params on the guest side."""
    count_map = _find_count_fields(params, reg)

    # First pass: count fields
    for p in params:
        if p.name is None:
            continue
        if not p.input:
            continue
        if p.name in count_map:
            if p.indirection >= 1:
                out.write(f'    {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
                if p.const:
                    deref = f'*({p.type_name} *)'
                else:
                    deref = '*'
            else:
                deref = ''
            out.write(f'    switch (style) {{\n')
            out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NONNULL:\n')
            out.write(f'    case NPT_STYLE_COUNT_ZERO_PTR_NULL:\n')
            out.write(f'        {deref}{prefix}{p.name} = 0;\n')
            out.write(f'        break;\n')
            out.write(f'    case NPT_STYLE_COUNT_ONE:\n')
            out.write(f'        {deref}{prefix}{p.name} = 1;\n')
            out.write(f'        break;\n')
            out.write(f'    case NPT_STYLE_COUNT_NONZERO:\n')
            out.write(f'    default:\n')
            out.write(f'        {deref}{prefix}{p.name} = 5;\n')
            out.write(f'        break;\n')
            out.write(f'    }}\n')

    # Second pass: other fields
    for p in params:
        if p.name is None:
            continue
        if not p.input:
            continue
        if p.name in count_map:
            continue

        cls = classify_field(reg, p)

        if cls == 'NON_SERIALIZABLE':
            if p.optional:
                out.write(f'    {prefix}{p.name} = NULL;\n')
            continue

        if cls in ('COM_HANDLE', 'INTERFACE_REF'):
            out.write(f'    {prefix}{p.name} = '
                      f'({_param_cast_type(p)})npt_test_handle_create(&seed);\n')
            continue

        if cls == 'WIN32_HANDLE':
            if p.indirection >= 1:
                out.write(f'    {prefix}{p.name} = npt_test_handle_create(&seed);\n')
            else:
                out.write(f'    {prefix}{p.name} = '
                          f'({p.type_name})(uintptr_t)npt_test_handle_create(&seed);\n')
            continue

        if cls == 'COM_HANDLE_ARRAY':
            cnt = get_count_expr(p, prefix, fields_map)
            if cnt:
                out.write(f'    if ({cnt} > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof(void *) * {cnt});\n')
                out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                out.write(f'            {prefix}{p.name}[_i] = npt_test_handle_create(&seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }}\n')
            continue

        if cls == 'STRING':
            out.write(f'    {prefix}{p.name} = ({p.type_name} *)npt_test_string(&seed, 8);\n')
            continue

        if cls == 'WSTRING':
            out.write(f'    {prefix}{p.name} = ({p.type_name} *)npt_test_wstring(&seed, 8);\n')
            continue

        if cls == 'STRING_ARRAY':
            cnt = get_count_expr(p, prefix, fields_map)
            is_wide = _is_wide_string_field(reg, p)
            str_fn = 'npt_test_wstring' if is_wide else 'npt_test_string'
            if cnt:
                out.write(f'    if ({cnt} > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof(void *) * {cnt});\n')
                out.write(f'        for (uint32_t _i = 0; _i < (uint32_t){cnt}; _i++)\n')
                out.write(f'            {prefix}{p.name}[_i] = ({p.type_name} *){str_fn}(&seed, 6);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }}\n')
            continue

        if cls == 'BLOB':
            cnt = get_count_expr(p, prefix, fields_map)
            if cnt:
                out.write(f'    {{ size_t _cnt = npt_test_clamp_count({cnt}, 1);\n')
                out.write(f'    if (_cnt > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(_cnt);\n')
                out.write(f'        npt_test_fill((void *){prefix}{p.name}, _cnt, &seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }} }}\n')
            continue

        if cls in ('FIXED_ARRAY', 'COUNTED_ARRAY'):
            cnt = get_count_expr(p, prefix, fields_map)
            if cnt:
                base = reg.resolve_alias_chain(p.type_name)
                is_prim = base in PRIMITIVE_NAMES or reg.is_enum(p)
                out.write(f'    {{ size_t _cnt = npt_test_clamp_count({cnt}, sizeof({p.type_name}));\n')
                out.write(f'    if (_cnt > 0) {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}) * _cnt);\n')
                if is_prim:
                    out.write(f'        npt_test_fill((void *){prefix}{p.name}, '
                              f'sizeof({p.type_name}) * _cnt, &seed);\n')
                else:
                    t2 = reg.types.get(p.type_name)
                    if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                        if t2.category == 'union' and t2.fields:
                            mf = t2.fields[0]
                            out.write(f'        for (uint32_t _i = 0; _i < (uint32_t)_cnt; _i++)\n')
                            out.write(f'            init_{p.type_name}__{mf.name}'
                                      f'(&(({p.type_name} *){prefix}{p.name})[_i], style, &seed, 1);\n')
                        else:
                            out.write(f'        for (uint32_t _i = 0; _i < (uint32_t)_cnt; _i++)\n')
                            out.write(f'            init_{p.type_name}'
                                      f'(&(({p.type_name} *){prefix}{p.name})[_i], style, &seed, 1);\n')
                    else:
                        out.write(f'        npt_test_fill((void *){prefix}{p.name}, '
                                  f'sizeof({p.type_name}) * _cnt, &seed);\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) ? NULL : npt_test_alloc(1);\n')
                out.write(f'    }} }}\n')
            continue

        if cls == 'SIMPLE_POINTER':
            if p.optional:
                out.write(f'    if (style == NPT_STYLE_COUNT_ZERO_PTR_NULL) {{\n')
                out.write(f'        {prefix}{p.name} = NULL;\n')
                out.write(f'    }} else {{\n')
                out.write(f'        {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
                _init_struct_or_fill(out, reg, p, prefix, indent=2)
                out.write(f'    }}\n')
            else:
                out.write(f'    {prefix}{p.name} = npt_test_alloc(sizeof({p.type_name}));\n')
                _init_struct_or_fill(out, reg, p, prefix, indent=1)
            continue

        if cls == 'SCALAR':
            if p.name not in count_map:
                t2 = reg.types.get(p.type_name)
                if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
                    if t2.category == 'union' and t2.fields:
                        mf = t2.fields[0]
                        out.write(f'    init_{p.type_name}__{mf.name}'
                                  f'(&{prefix}{p.name}, style, &seed, 1);\n')
                    else:
                        out.write(f'    init_{p.type_name}'
                                  f'(&{prefix}{p.name}, style, &seed, 1);\n')
                elif t2 and t2.category in ('struct', 'union'):
                    # Builtin or anonymous struct: fill with random data
                    out.write(f'    npt_test_fill(&{prefix}{p.name}, sizeof({p.type_name}), &seed);\n')
                else:
                    out.write(f'    {prefix}{p.name} = ({p.type_name})npt_test_rand(&seed);\n')
            continue

        if cls == 'BITFIELD':
            mask = (1 << p.bitwidth) - 1
            out.write(f'    {prefix}{p.name} = npt_test_rand(&seed) & 0x{mask:x}u;\n')
            continue


def _init_struct_or_fill(out, reg, p, prefix, indent=1):
    """Initialize a pointed-to struct or fill with random data."""
    ind = '    ' * indent
    t2 = reg.types.get(p.type_name)
    if t2 and t2.category in ('struct', 'union') and t2.name not in BUILTIN_STRUCT_NAMES and not t2.is_anonymous:
        if t2.category == 'union' and t2.fields:
            mf = t2.fields[0]
            out.write(f'{ind}init_{p.type_name}__{mf.name}'
                      f'(({p.type_name} *){prefix}{p.name}, style, &seed, 1);\n')
        else:
            out.write(f'{ind}init_{p.type_name}'
                      f'(({p.type_name} *){prefix}{p.name}, style, &seed, 1);\n')
    else:
        out.write(f'{ind}npt_test_fill((void *){prefix}{p.name}, '
                  f'sizeof({p.type_name}), &seed);\n')


# ---------------------------------------------------------------------------
# Generate test_roundtrip.c (main runner)
# ---------------------------------------------------------------------------

def generate_main(testable_structs, testable_methods):
    out = StringIO()
    out.write('/* Auto-generated by npt_testgen.py -- do not edit. */\n\n')
    out.write('#include <stdio.h>\n')
    out.write('#include <stdlib.h>\n')
    out.write('#include <string.h>\n')
    out.write('#include <stdint.h>\n')
    out.write('#include "npt_test_ids.h"\n\n')

    out.write('extern int host_test_struct(int test_id, int style);\n')
    out.write('extern int guest_encode_command(int test_id, int style, '
              'uint8_t *buf, size_t buf_size, size_t *out_size);\n')
    out.write('extern int host_verify_command(int test_id, int style, '
              'const uint8_t *buf, size_t size);\n')
    out.write('extern int host_encode_reply(int test_id, int style, '
              'uint8_t *buf, size_t buf_size, size_t *out_size);\n')
    out.write('extern int guest_verify_reply(int test_id, int style, '
              'const uint8_t *buf, size_t size);\n\n')

    # Struct test table
    out.write('struct test_entry {\n')
    out.write('    int test_id;\n')
    out.write('    const char *name;\n')
    out.write('};\n\n')

    out.write(f'static const struct test_entry struct_tests[] = {{\n')
    for i, (t, member, anon_variant) in enumerate(testable_structs):
        suffix = f'__{member}' if member else (f'__{anon_variant[1]}' if anon_variant else '')
        out.write(f'    {{ {i}, "{t.name}{suffix}" }},\n')
    out.write(f'}};\n')
    out.write(f'#define NUM_STRUCT_TESTS {len(testable_structs)}\n\n')

    # Method test table
    out.write('struct method_test_entry {\n')
    out.write('    int test_id;\n')
    out.write('    const char *name;\n')
    out.write('    int has_reply;\n')
    out.write('    int has_count_output;\n')
    out.write('};\n\n')

    out.write(f'static const struct method_test_entry method_tests[] = {{\n')
    for i, (iface, method, fname, is_toplevel) in enumerate(testable_methods):
        has_reply = 1 if method_has_output(method) else 0
        has_co = 1 if method_has_count_output(method) else 0
        out.write(f'    {{ {i}, "{fname}", {has_reply}, {has_co} }},\n')
    out.write(f'}};\n')
    out.write(f'#define NUM_METHOD_TESTS {len(testable_methods)}\n\n')

    # Main
    out.write('int main(void)\n{\n')
    out.write('    int pass = 0, fail = 0;\n')
    out.write('    const size_t BUF_SIZE = 1u << 20;\n')
    out.write('    uint8_t *buf = (uint8_t *)calloc(1, BUF_SIZE);\n')



    # Struct tests (styles 0-3)
    out.write('    /* Struct roundtrip tests */\n')
    out.write('    for (int i = 0; i < NUM_STRUCT_TESTS; i++) {\n')
    out.write('        for (int style = 0; style <= NPT_STYLE_COUNT_NONZERO; style++) {\n')
    out.write('            int r = host_test_struct(struct_tests[i].test_id, style);\n')
    out.write('            if (r == 0) {\n')
    out.write('                pass++;\n')
    out.write('            } else {\n')
    out.write('                fprintf(stderr, "FAIL: struct %s style %d\\n", struct_tests[i].name, style);\n')
    out.write('                fail++;\n')
    out.write('            }\n')
    out.write('        }\n')
    out.write('    }\n\n')

    # Method command tests (styles 0-3)
    out.write('    /* Method command roundtrip tests (guest encode -> host verify) */\n')
    out.write('    for (int i = 0; i < NUM_METHOD_TESTS; i++) {\n')
    out.write('        for (int style = 0; style <= NPT_STYLE_COUNT_NONZERO; style++) {\n')
    out.write('            size_t cmd_size = 0;\n')
    out.write('            int r = guest_encode_command(method_tests[i].test_id, style, buf, BUF_SIZE, &cmd_size);\n')
    out.write('            if (r != 0) { fail++; continue; }\n')
    out.write('            r = host_verify_command(method_tests[i].test_id, style, buf, cmd_size);\n')
    out.write('            if (r == 0) {\n')
    out.write('                pass++;\n')
    out.write('            } else {\n')
    out.write('                fprintf(stderr, "FAIL: CMD %s style %d\\n", method_tests[i].name, style);\n')
    out.write('                fail++;\n')
    out.write('            }\n')
    out.write('            memset(buf, 0, cmd_size); /* clear for next encode */\n')
    out.write('        }\n')
    out.write('    }\n\n')

    # Method reply tests
    out.write('    /* Method reply roundtrip tests (host encode -> guest verify) */\n')
    out.write('    for (int i = 0; i < NUM_METHOD_TESTS; i++) {\n')
    out.write('        if (!method_tests[i].has_reply) continue;\n')
    out.write('        int max_style = method_tests[i].has_count_output\n')
    out.write('            ? NPT_STYLE_COUNT_OUTPUT_ERROR_ZERO\n')
    out.write('            : NPT_STYLE_COUNT_NONZERO;\n')
    out.write('        for (int style = 0; style <= max_style; style++) {\n')
    out.write('            size_t reply_size = 0;\n')
    out.write('            int r = host_encode_reply(method_tests[i].test_id, style, buf, BUF_SIZE, &reply_size);\n')
    out.write('            if (r != 0) { fail++; continue; }\n')
    out.write('            r = guest_verify_reply(method_tests[i].test_id, style, buf, reply_size);\n')
    out.write('            if (r == 0) {\n')
    out.write('                pass++;\n')
    out.write('            } else {\n')
    out.write('                fprintf(stderr, "FAIL: REPLY %s style %d\\n", method_tests[i].name, style);\n')
    out.write('                fail++;\n')
    out.write('            }\n')
    out.write('            memset(buf, 0, reply_size); /* clear for next encode */\n')
    out.write('        }\n')
    out.write('    }\n\n')

    # Manual tests (from test_roundtrip_manual.c)
    out.write('    /* Manual roundtrip tests for types with incompatible unions */\n')
    out.write('    extern int manual_test_count(void);\n')
    out.write('    extern int run_manual_test(int index);\n')
    out.write('    extern const char *manual_test_name(int index);\n')
    out.write('    for (int i = 0; i < manual_test_count(); i++) {\n')
    out.write('        int r = run_manual_test(i);\n')
    out.write('        if (r == 0) {\n')
    out.write('            pass++;\n')
    out.write('        } else {\n')
    out.write('            fprintf(stderr, "FAIL: manual %s\\n", manual_test_name(i));\n')
    out.write('            fail++;\n')
    out.write('        }\n')
    out.write('    }\n\n')

    out.write('    printf("Results: %d passed, %d failed\\n", pass, fail);\n')
    out.write('    free(buf);\n')
    out.write('    return fail > 0 ? 1 : 0;\n')
    out.write('}\n')

    return out.getvalue()


# ---------------------------------------------------------------------------
# Write-if-changed helper
# ---------------------------------------------------------------------------

def write_if_changed(path, content):
    """Only write the file if the content differs."""
    path = Path(path)
    if path.exists():
        existing = path.read_text()
        if existing == content:
            path.touch()
            return False
    path.write_text(content)
    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Neptune protocol test generator')
    parser.add_argument('--outdir', required=True, type=Path,
                        help='Output directory for generated test files')
    parser.add_argument('--json', required=True, type=Path,
                        help='Path to npt_registry.json')
    parser.add_argument('--overlay', action='append', type=Path, default=[],
                        help='Path to overlay JSON (can be specified multiple times)')
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    # Load registry
    print(f'Loading {args.json}...')
    reg = Registry()
    reg.load(args.json, args.overlay)

    print(f'  {len(reg.interfaces)} interfaces, '
          f'{len(reg.functions)} functions, '
          f'{len(reg.structs)} structs, '
          f'{len(reg.unions)} unions')

    # Collect testable items
    testable_structs = collect_testable_structs(reg)
    testable_methods = collect_testable_methods(reg)

    total_structs = len(reg.structs) + len(reg.unions)
    total_methods = sum(len(i.methods) for i in reg.interfaces) + len(reg.functions)
    skipped_structs = total_structs - len(testable_structs)
    skipped_methods = total_methods - len(testable_methods)
    print(f'  {len(testable_structs)} testable struct/union entries '
          f'({skipped_structs} skipped), '
          f'{len(testable_methods)} testable methods/functions '
          f'({skipped_methods} skipped)')

    # Collect init dependencies
    init_types = collect_init_deps(reg, testable_structs, testable_methods)

    # Generate files
    content = generate_test_ids(testable_structs, testable_methods)
    if write_if_changed(args.outdir / 'npt_test_ids.h', content):
        print(f'  wrote npt_test_ids.h')

    content = generate_host(reg, testable_structs, testable_methods, init_types)
    if write_if_changed(args.outdir / 'test_roundtrip_host.c', content):
        print(f'  wrote test_roundtrip_host.c')

    content = generate_guest(reg, testable_methods, init_types)
    if write_if_changed(args.outdir / 'test_roundtrip_guest.c', content):
        print(f'  wrote test_roundtrip_guest.c')

    content = generate_main(testable_structs, testable_methods)
    if write_if_changed(args.outdir / 'test_roundtrip.c', content):
        print(f'  wrote test_roundtrip.c')

    print('Done.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
