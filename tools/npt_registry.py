#!/usr/bin/env python3

# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

"""
Neptune protocol type registry.

Loads npt_protocol.json + overlay(s), merges them, and builds a typed
registry of all enums, structs, unions, interfaces, and functions used
by the code generator.
"""

import json
import re
import sys
from dataclasses import dataclass, field as dataclass_field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class Category(IntEnum):
    PRIMITIVE = 0
    ALIAS = 1
    ENUM = 2
    STRUCT = 3
    UNION = 4
    INTERFACE = 5
    FUNCTION = 6
    CONST = 7

PRIMITIVE_NAMES = {
    'uint8_t', 'int8_t',
    'uint16_t', 'int16_t',
    'uint32_t', 'int32_t',
    'uint64_t', 'int64_t',
    'float', 'double',
}

# Wire sizes (padded to 32-bit minimum)
PRIMITIVE_WIRE_SIZES = {
    'uint8_t': 4, 'int8_t': 4,
    'uint16_t': 4, 'int16_t': 4,
    'uint32_t': 4, 'int32_t': 4,
    'float': 4,
    'uint64_t': 8, 'int64_t': 8,
    'double': 8,
}

# Native sizes (actual C sizeof)
PRIMITIVE_NATIVE_SIZES = {
    'uint8_t': 1, 'int8_t': 1,
    'uint16_t': 2, 'int16_t': 2,
    'uint32_t': 4, 'int32_t': 4,
    'float': 4,
    'uint64_t': 8, 'int64_t': 8,
    'double': 8,
}

# Types that are string bases for implicit-length encoding.
# Only type *names* that explicitly represent strings, not the underlying
# primitive (uint16_t could be a non-string buffer).
STRING_TYPES = {'CHAR', 'char'}
WSTRING_TYPES = {'WCHAR', 'wchar_t'}

# Types that cannot be serialized (no meaningful wire representation).
# void/VOID are only non-serializable when used as bare pointers without
# a byte count; void* WITH a count is a blob.  The others are opaque
# OS types that must be handled out-of-band.
NON_SERIALIZABLE_TYPES = {'void', 'VOID', 'PFN_DESTRUCTION_CALLBACK',
                          'SECURITY_ATTRIBUTES', 'HDC'}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class NptField:
    """A struct/union field or function/method parameter."""
    name: Optional[str]
    type_name: str           # raw type name string (or None for inline)
    type_ref: Optional['NptType'] = None  # resolved after registry build
    inline_type: Optional[dict] = None    # raw dict for anonymous inline types
    indirection: int = 0
    const: bool = False
    count: Any = None        # element count: str (field name), int, list, or None
    count_output: Optional[str] = None  # output count field name (for _Out_writes_to_)
    bitwidth: Optional[int] = None
    condition: Any = None    # str, bool, or None
    value: Optional[int] = None  # for enum fields
    handle: Optional[str] = None  # 'com', 'win32', or None
    input: bool = True
    output: bool = False
    optional: bool = False
    idl_param_index: Optional[int] = None
    # Computed: number of pointer dereferences needed to read the count value.
    # -1 means "not a sibling field — don't prefix" (global constant).
    _size_deref: int = -1
    _size_output_deref: int = -1

    @property
    def is_handle(self):
        return self.handle in ('com', 'win32')

    @property
    def is_com_handle(self):
        return self.handle == 'com'

    @property
    def is_win32_handle(self):
        return self.handle == 'win32'

    @property
    def is_blob(self):
        """True if void/VOID pointer with a size annotation."""
        return (self.type_name in ('void', 'VOID') and self.indirection == 1
                and self.count is not None)

    @property
    def is_fixed_array(self):
        """True if the field is a fixed-size embedded array (never NULL)."""
        if isinstance(self.count, (int, list)):
            return True
        return isinstance(self.count, str) and self.count.strip().isdigit()

    @property
    def is_enum(self):
        return self.type_ref is not None and self.type_ref.category == Category.ENUM

    @property
    def is_struct(self):
        return self.type_ref is not None and self.type_ref.category == Category.STRUCT

    @property
    def is_union(self):
        return self.type_ref is not None and self.type_ref.category == Category.UNION

    @property
    def is_anonymous_type(self):
        """True if the referenced type is a synthetic anonymous struct/union."""
        return self.type_ref is not None and self.type_ref.is_anonymous

    @property
    def is_non_serializable(self):
        """True if the type cannot be serialized (excludes blobs and handles)."""
        return (self.type_name in NON_SERIALIZABLE_TYPES and
                not self.is_handle and
                not (self.indirection >= 1 and self.count is not None))


@dataclass
class NptMethod:
    """An interface method."""
    name: str
    return_type: Optional[str] = None
    params: list[NptField] = dataclass_field(default_factory=list)
    wire_index: int = 0       # 0-based within this interface's own methods
    vtable_index: int = 0     # absolute vtable slot (including inherited)
    id: Optional[int] = None  # explicit vtable id from JSON

    # Guest-proxy-only annotation: when true, the generator emits ONLY a
    # forward declaration of the default thunk -- the consumer (mesa) MUST
    # provide a hand-written body or the link fails.  Use this for methods
    # whose parameters cannot be auto-marshalled (e.g. CreateBuffer takes a
    # D3D11_SUBRESOURCE_DATA whose pSysMem is an unsized const void *).
    # Without this flag the generator would emit a default thunk that calls
    # the encoder which silently drops the un-serializable data.
    skip_default: bool = False

    # Guest-proxy-only annotation: when true, the generator emits a sync
    # (npt_call_) thunk regardless of multi_ring_enabled.  Use for methods
    # whose HRESULT carries control-flow meaning rather than fatal-error
    # semantics -- enumeration terminators like IDXGIAdapter::EnumOutputs
    # signal end-of-iteration with DXGI_ERROR_NOT_FOUND, and the
    # async/deferred-fatal optimization would mask that into a fake S_OK
    # and make the caller loop forever.
    force_sync: bool = False


@dataclass
class NptType:
    """A type in the registry."""
    name: Optional[str]
    primitive: str
    category: Category
    source: Optional[str] = None

    # For aliases: the target primitive name
    alias_target: Optional[str] = None

    # For enums
    fields: list[NptField] = dataclass_field(default_factory=list)

    # For structs/unions
    # (fields is reused)

    # For interfaces
    methods: list[NptMethod] = dataclass_field(default_factory=list)
    parent_name: Optional[str] = None
    parent: Optional['NptType'] = None  # resolved
    uuid: Optional[str] = None
    uuid_hash: int = 0
    uuid_bytes: Optional[bytes] = None
    # Pinned interface id from npt_interface_ids.json.  Unique across the
    # registry.  Used as the wire-format routing key (replaces uuid_hash
    # for dispatch) and as the object_type tag in the host runtime.
    interface_id: int = -1

    # For functions
    return_type: Optional[str] = None
    group: Optional[int] = None
    id: Optional[int] = None
    params: list[NptField] = dataclass_field(default_factory=list)

    # For consts
    value: Optional[int] = None

    # Computed
    vtable_base: int = 0       # first vtable slot for this interface's own methods
    total_vtable_count: int = 0  # total vtable slots including inherited
    is_anonymous: bool = False   # True for synthetic types from inline definitions
    family: Optional[str] = None  # interface family (root ancestor name, lowercased)

    def parent_chain(self):
        """
        Return the list of ancestor interfaces from the topmost (just below
        IUnknown) down to but NOT including self.  Used by the guest proxy
        generator to enumerate vtable slots in COM ABI order.

        Excludes IUnknown -- it has special handling (slots 0-2 are
        QueryInterface/AddRef/Release, supplied by the runtime layer).
        """
        chain = []
        cur = self.parent
        while cur is not None and cur.name != 'IUnknown':
            chain.append(cur)
            cur = cur.parent
        chain.reverse()
        return chain

    def iter_vtable_methods(self):
        """
        Yield (owning_iface, method) tuples in COM vtable order, walking the
        parent chain.  Skips IUnknown methods (slots 0-2 are runtime-provided).
        Slot 3 onward maps to: parent[0].methods, parent[1].methods, ...,
        self.methods.
        """
        for ancestor in self.parent_chain():
            for m in ancestor.methods:
                yield ancestor, m
        for m in self.methods:
            yield self, m

    def parent_iid_chain_names(self):
        """
        Return the list of interface names in the parent IID chain that
        QueryInterface can fast-path-claim against.  Always starts with
        IUnknown (every COM object answers to it), then any ancestors (in
        topmost-first order), then self.

        Used to generate the parent_iid_chain table for the proxy.
        """
        names = ['IUnknown']
        names.extend(a.name for a in self.parent_chain())
        names.append(self.name)
        return names


# ---------------------------------------------------------------------------
# Overlay merge
# ---------------------------------------------------------------------------

_TYPED_ARRAY_KEYS = {'types', 'fields', 'methods', 'params'}


def _is_typed_object_array(key, val):
    return key in _TYPED_ARRAY_KEYS and isinstance(val, list)


def _find_match(base_arr, ov_elem):
    if 'index' in ov_elem:
        idx = ov_elem['index']
        if 0 <= idx < len(base_arr):
            return idx
        print(f"WARNING: overlay index {idx} out of range for array of "
              f"length {len(base_arr)} (element: {ov_elem.get('name', '?')})",
              file=sys.stderr)
        return None
    if 'name' in ov_elem and ov_elem['name'] is not None:
        for i, base_elem in enumerate(base_arr):
            if isinstance(base_elem, dict) and base_elem.get('name') == ov_elem['name']:
                return i
    return None


# NOTE: _find_match / _merge_objects / _merge_typed_array / merge_overlay
# are duplicated in tools/npt_testgen.py — keep them in sync.
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
        if key in base_obj and _is_typed_object_array(key, ov_val):
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
    """Merge an overlay JSON dict into the base JSON dict (in-place)."""
    if base.get('version') != overlay.get('version'):
        raise ValueError(
            f"Version mismatch: base={base.get('version')} "
            f"overlay={overlay.get('version')}")
    _merge_typed_array(base.setdefault('types', []), overlay.get('types', []))


# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------

def parse_uuid(uuid_str):
    """Parse a UUID string like '189819f1-1db6-4b57-be54-1821339b85f7' into 16 bytes."""
    clean = uuid_str.replace('-', '')
    return bytes.fromhex(clean)


def uuid_hash(uuid_bytes):
    """Compute an 8-bit hash from 16-byte UUID for dispatch routing."""
    # Simple XOR fold of all bytes
    h = 0
    for b in uuid_bytes:
        h ^= b
    return h & 0xFF


def uuid_to_guid_init(uuid_str):
    """Convert UUID string to C GUID initializer components."""
    parts = uuid_str.split('-')
    data1 = int(parts[0], 16)
    data2 = int(parts[1], 16)
    data3 = int(parts[2], 16)
    data4_hex = parts[3] + parts[4]
    data4 = [int(data4_hex[i:i+2], 16) for i in range(0, 16, 2)]
    return data1, data2, data3, data4


# ---------------------------------------------------------------------------
# Count expression helper
# ---------------------------------------------------------------------------

_INEXPRESSIBLE_RE = re.compile(r'^_Inexpressible_\((.+)\)$')


def parse_count_expr(count_str):
    """Parse a count/size string, unwrapping ``_Inexpressible_(...)``.

    Returns the inner expression string (suitable for emission as C), or
    ``None`` if the field is unsized (quoted ``_Inexpressible_`` form or a
    bare ``_SAL_``-style annotation we cannot interpret).
    """
    m = _INEXPRESSIBLE_RE.match(count_str)
    if m:
        inner = m.group(1)
        if inner.startswith('"'):
            return None
        return inner
    if count_str.startswith('_'):
        return None
    return count_str


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------

def _strip_type_prefix(name):
    """Strip C 'struct ', 'union ', 'enum ' prefix from a type name."""
    for prefix in ('struct ', 'union ', 'enum '):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _parse_field(raw, parent_name=None, index=0):
    """Parse a raw JSON field/param dict into an NptField."""
    type_val = raw.get('type', 'void')
    inline_type = None
    type_name = None

    if isinstance(type_val, dict):
        # Anonymous inline type
        inline_type = type_val
        type_name = None  # will be resolved to synthetic type
    else:
        type_name = _strip_type_prefix(type_val)

    return NptField(
        name=raw.get('name'),
        type_name=type_name or '',
        inline_type=inline_type,
        indirection=raw.get('indirection', 0),
        const=raw.get('const', False),
        count=raw.get('count'),
        count_output=raw.get('count_output'),
        bitwidth=raw.get('bitwidth'),
        condition=raw.get('condition'),
        value=raw.get('value'),
        handle=raw.get('handle'),
        input=raw.get('input', True),
        output=raw.get('output', False),
        optional=raw.get('optional', False),
        idl_param_index=raw.get('idl_param_index'),
    )


def _parse_method(raw, index):
    """Parse a raw JSON method dict into an NptMethod."""
    params = []
    for i, p in enumerate(raw.get('params', [])):
        params.append(_parse_field(p, parent_name=raw.get('name'), index=i))

    return NptMethod(
        name=raw['name'],
        return_type=raw.get('return'),
        params=params,
        wire_index=raw.get('index', index),
        id=raw.get('id'),
        skip_default=bool(raw.get('skip_default', False)),
        force_sync=bool(raw.get('force_sync', False)),
    )


# ---------------------------------------------------------------------------
# Type registry
# ---------------------------------------------------------------------------

class TypeRegistry:
    """
    Central registry of all Neptune protocol types.

    Call load() to parse JSON and overlays, then resolve() to link
    type references and compute vtable indices.
    """

    def __init__(self):
        self.source_files: list[str] = []  # original IDL source file names
        self.types: dict[str, NptType] = {}
        self.anonymous_types: list[NptType] = []  # inline anonymous types
        self.interfaces: list[NptType] = []
        self.functions: list[NptType] = []
        self.structs: list[NptType] = []
        self.enums: list[NptType] = []
        self.unions: list[NptType] = []
        self.consts: list[NptType] = []
        self.aliases: list[NptType] = []
        self._warnings: list[str] = []

    def warn(self, msg):
        self._warnings.append(msg)
        print(f"WARNING: {msg}", file=sys.stderr)

    def load(self, json_path, overlay_paths=None, interface_ids_path=None):
        """Load base JSON and apply overlays, then pin interface ids."""
        with open(json_path, 'r') as f:
            base = json.load(f)

        self.source_files = base.get('source_files', [])
        self.version = base.get('version', 0)

        for overlay_path in (overlay_paths or []):
            with open(overlay_path, 'r') as f:
                overlay = json.load(f)
            merge_overlay(base, overlay)

        self._build_from_json(base)

        if interface_ids_path is not None:
            self._load_interface_ids(interface_ids_path)

    def _load_interface_ids(self, path):
        """
        Load npt_interface_ids.json and pin each interface's wire-format
        id.  Enforces:
          - no duplicate ids (JSON keys are unique by parse, but we
            also reject non-integer keys);
          - no duplicate GUIDs in the file;
          - every registry interface has an entry whose name matches;
          - every non-retired entry in the file exists in the registry
            under the recorded name.  Retired entries keep their slot
            forever (protobuf field-number policy) and do not need a
            registry match.

        Any mismatch is an error (stderr + non-zero exit) so a missing
        pin cannot silently regress.  The error message tells the dev
        to run tools/npt_allocate_interface_id.py.
        """
        with open(path, 'r') as f:
            data = json.load(f)

        # Canonicalise: int keys, lower-case GUIDs, validate shape.
        entries = {}        # id -> (guid_lower, name, retired_bool)
        guid_to_id = {}     # guid_lower -> id
        name_to_id = {}     # name -> id (non-retired only)
        for k, v in data.items():
            try:
                iid = int(k)
            except ValueError:
                sys.exit(f"error: {path}: key {k!r} is not an integer")
            if iid < 0:
                sys.exit(f"error: {path}: id {iid} is negative")
            if iid in entries:
                sys.exit(f"error: {path}: duplicate id {iid}")
            guid = v.get('guid', '').lower()
            name = v.get('name', '')
            retired = bool(v.get('retired', False))
            if not guid or not name:
                sys.exit(f"error: {path}: entry {iid} missing guid/name")
            if guid in guid_to_id and not retired:
                sys.exit(
                    f"error: {path}: guid {guid} appears on id {iid} and "
                    f"id {guid_to_id[guid]}")
            entries[iid] = (guid, name, retired)
            guid_to_id[guid] = iid
            if not retired:
                if name in name_to_id:
                    sys.exit(
                        f"error: {path}: non-retired name {name!r} appears "
                        f"on id {iid} and id {name_to_id[name]}")
                name_to_id[name] = iid

        # Pin each registry interface.
        missing = []
        for iface in self.types.values():
            if iface.category != Category.INTERFACE or not iface.uuid:
                continue
            guid = iface.uuid.lower()
            iid = guid_to_id.get(guid)
            if iid is None:
                missing.append(iface)
                continue
            _, pinned_name, retired = entries[iid]
            if retired:
                sys.exit(
                    f"error: {path}: interface {iface.name} (guid {guid}) "
                    f"maps to id {iid} which is marked retired; allocate a "
                    f"new id via tools/npt_allocate_interface_id.py")
            if pinned_name != iface.name:
                sys.exit(
                    f"error: {path}: id {iid} pins name {pinned_name!r} but "
                    f"the registry has {iface.name!r} for guid {guid}; "
                    f"rename drift -- update the pin or the registry")
            iface.interface_id = iid

        if missing:
            names = ', '.join(f"{t.name} ({t.uuid})" for t in missing)
            sys.exit(
                f"error: {path}: no pin for interfaces: {names}\n"
                f"       run: for each above,\n"
                f"         python3 tools/npt_allocate_interface_id.py "
                f"<name> <guid>")

        # Reverse check: every non-retired pin must correspond to a live
        # interface in the registry (catches a registry regen that dropped
        # an interface without marking it retired).
        live_guids = {
            iface.uuid.lower()
            for iface in self.types.values()
            if iface.category == Category.INTERFACE and iface.uuid
        }
        for iid, (guid, name, retired) in entries.items():
            if retired:
                continue
            if guid not in live_guids:
                sys.exit(
                    f"error: {path}: id {iid} ({name}, guid {guid}) is not "
                    f"present in the registry; mark the entry "
                    f"\"retired\": true if the interface has been dropped")

    def _categorize_primitive(self, prim, name=None):
        """Determine category from a primitive string."""
        if prim in PRIMITIVE_NAMES:
            # Only the primitive type itself (e.g. name='uint32_t') is PRIMITIVE.
            # An alias like name='UINT', primitive='uint32_t' is ALIAS.
            if name is None or name == prim:
                return Category.PRIMITIVE
            return Category.ALIAS
        if prim == 'enum':
            return Category.ENUM
        if prim == 'struct':
            return Category.STRUCT
        if prim == 'union':
            return Category.UNION
        if prim == 'interface':
            return Category.INTERFACE
        if prim == 'function':
            return Category.FUNCTION
        if prim == 'const':
            return Category.CONST
        # Anything else is an alias (e.g. UINT -> uint32_t, GUID -> struct)
        return Category.ALIAS

    def _build_from_json(self, data):
        """Parse all types from merged JSON data."""
        # First pass: create NptType objects
        for raw in data.get('types', []):
            name = raw.get('name')
            prim = raw.get('primitive', '')
            cat = self._categorize_primitive(prim, name)

            ntype = NptType(
                name=name,
                primitive=prim,
                category=cat,
                source=raw.get('source'),
            )

            if cat == Category.ALIAS:
                ntype.alias_target = prim

            elif cat == Category.ENUM:
                for i, f in enumerate(raw.get('fields', [])):
                    ntype.fields.append(_parse_field(f, parent_name=name, index=i))

            elif cat in (Category.STRUCT, Category.UNION):
                for i, f in enumerate(raw.get('fields', [])):
                    ntype.fields.append(_parse_field(f, parent_name=name, index=i))

            elif cat == Category.INTERFACE:
                ntype.parent_name = raw.get('parent')
                ntype.uuid = raw.get('uuid')
                if ntype.uuid:
                    ntype.uuid_bytes = parse_uuid(ntype.uuid)
                    ntype.uuid_hash = uuid_hash(ntype.uuid_bytes)
                for i, m in enumerate(raw.get('methods', [])):
                    ntype.methods.append(_parse_method(m, i))

            elif cat == Category.FUNCTION:
                ntype.return_type = raw.get('return')
                ntype.group = raw.get('group')
                ntype.id = raw.get('id')
                for i, p in enumerate(raw.get('params', [])):
                    ntype.params.append(_parse_field(p, parent_name=name, index=i))

            elif cat == Category.CONST:
                ntype.value = raw.get('value')

            if name:
                self.types[name] = ntype

        # Add built-in IUnknown (not in JSON)
        if 'IUnknown' not in self.types:
            iunknown = NptType(
                name='IUnknown',
                primitive='interface',
                category=Category.INTERFACE,
                uuid='00000000-0000-0000-c000-000000000046',
                parent_name=None,
            )
            iunknown.uuid_bytes = parse_uuid(iunknown.uuid)
            iunknown.uuid_hash = uuid_hash(iunknown.uuid_bytes)
            # IUnknown has 3 methods but we don't serialize them
            # (QueryInterface/AddRef/Release are handled by the runtime)
            iunknown.total_vtable_count = 3
            self.types['IUnknown'] = iunknown

        # Add built-in GUID if not present
        if 'GUID' not in self.types:
            guid_type = NptType(
                name='GUID',
                primitive='struct',
                category=Category.STRUCT,
            )
            self.types['GUID'] = guid_type

        # Add built-in POINT { LONG x; LONG y; } if not present
        if 'POINT' not in self.types:
            point_type = NptType(
                name='POINT',
                primitive='struct',
                category=Category.STRUCT,
            )
            point_type.fields = [
                NptField(name='x', type_name='LONG'),
                NptField(name='y', type_name='LONG'),
            ]
            self.types['POINT'] = point_type

        # Add built-in RECT { LONG left, top, right, bottom; } if not present
        if 'RECT' not in self.types:
            rect_type = NptType(
                name='RECT',
                primitive='struct',
                category=Category.STRUCT,
            )
            rect_type.fields = [
                NptField(name='left', type_name='LONG'),
                NptField(name='top', type_name='LONG'),
                NptField(name='right', type_name='LONG'),
                NptField(name='bottom', type_name='LONG'),
            ]
            self.types['RECT'] = rect_type

    def resolve(self):
        """Resolve type references, compute vtable indices, build category lists."""
        # Resolve anonymous inline types first
        self._resolve_anonymous_types()

        # Resolve field type references
        for ntype in self.types.values():
            for field in ntype.fields:
                self._resolve_field_type(field)
            for param in ntype.params:
                self._resolve_field_type(param)
            for method in ntype.methods:
                for param in method.params:
                    self._resolve_field_type(param)

        # Resolve interface parent references and compute vtable indices
        for ntype in self.types.values():
            if ntype.category == Category.INTERFACE:
                self._resolve_interface_chain(ntype)

        # Build category lists
        for ntype in self.types.values():
            if ntype.category == Category.INTERFACE:
                self.interfaces.append(ntype)
            elif ntype.category == Category.FUNCTION:
                if ntype.group is not None and ntype.id is not None:
                    self.functions.append(ntype)
            elif ntype.category == Category.STRUCT:
                self.structs.append(ntype)
            elif ntype.category == Category.ENUM:
                self.enums.append(ntype)
            elif ntype.category == Category.UNION:
                self.unions.append(ntype)
            elif ntype.category == Category.CONST:
                self.consts.append(ntype)
            elif ntype.category == Category.ALIAS:
                self.aliases.append(ntype)

        # Validate field constraints before code generation
        self._validate_fields()

        # Resolve size field dereference counts
        self._resolve_size_derefs()

        # Sort functions by group then id
        self.functions.sort(key=lambda f: (f.group, f.id))

    def _validate_fields(self):
        """Check for invalid field configurations that would produce broken code."""
        def check_field(field, context):
            # COM handle at indirection 1 with output flag is unsupported:
            # there's no caller slot to write back to.
            if (field.is_com_handle and field.indirection == 1
                    and field.output):
                raise ValueError(
                    f"degenerate output COM handle: '{field.name}' has "
                    f"indirection=1 with output=True in {context}; "
                    f"output COM handles must have indirection=2 (Foo**)")
            # Interface reference array without handle annotation would be
            # serialized as struct data instead of handle IDs.
            if (field.indirection >= 2 and field.count
                    and not field.is_handle and field.type_ref
                    and field.type_ref.category == Category.INTERFACE):
                raise ValueError(
                    f"interface reference array '{field.name}' "
                    f"(type={field.type_name}, "
                    f"indirection={field.indirection}) has count but no "
                    f"handle annotation in {context}; "
                    f"add handle='com' in the overlay")

        for ntype in self.types.values():
            ctx = ntype.name or '<anon>'
            for field in ntype.fields:
                check_field(field, ctx)
            for param in ntype.params:
                check_field(param, ctx)
            for method in ntype.methods:
                mctx = f'{ctx}.{method.name}'
                for param in method.params:
                    check_field(param, mctx)

    def _resolve_size_derefs(self):
        """For fields with string size references, compute how many
        dereferences are needed to get the count value.
        A size field at indirection 0 needs 0 derefs (val->Count).
        A size field at indirection 1 needs 1 deref (*val->pCount).
        Stores the result as field._size_deref and field._size_output_deref."""
        def resolve_fields(fields):
            field_map = {}
            # First pass: collect all accessible field names + their indirection
            # (including anonymous inner fields which are accessed through parent)
            def collect(flist):
                for f in flist:
                    if f.name:
                        field_map[f.name] = f.indirection
                    if f.name is None and f.type_ref and \
                            f.type_ref.category in (Category.STRUCT, Category.UNION):
                        collect(f.type_ref.fields)
            collect(fields)

            # Second pass: set deref counts
            # -1 means "not a sibling field — don't prefix" (global constant)
            def _resolve_count_str(s):
                """Check if a count string references known fields.
                Returns the max deref needed, or -1 if not all terms are fields."""
                parsed = parse_count_expr(s)
                if parsed is None:
                    return -1
                # Split on '*' for multiplication terms
                terms = [t.strip() for t in parsed.split('*')]
                max_deref = 0
                for term in terms:
                    if term.isdigit() or term.startswith('sizeof('):
                        continue
                    base = term.split('->')[0] if '->' in term else term
                    if base in field_map:
                        if field_map[base] > 1:
                            raise ValueError(
                                f"count field '{base}' has indirection "
                                f"{field_map[base]} (expected 0 or 1)")
                        max_deref = max(max_deref, field_map[base])
                    else:
                        return -1  # unknown term
                return max_deref

            def set_derefs(flist):
                for f in flist:
                    if isinstance(f.count, str):
                        f._size_deref = _resolve_count_str(f.count)
                    if f.count_output:
                        if f.count_output in field_map:
                            f._size_output_deref = field_map[f.count_output]
                    # Recurse into anonymous inner types
                    if f.name is None and f.type_ref and \
                            f.type_ref.category in (Category.STRUCT, Category.UNION):
                        set_derefs(f.type_ref.fields)
            set_derefs(fields)

        anon_names = {t.name for t in self.anonymous_types if t.name}
        for ntype in self.types.values():
            # Skip anonymous types — handled by recursion from parent
            if ntype.name in anon_names:
                continue
            if ntype.fields:
                resolve_fields(ntype.fields)
            if ntype.params:
                resolve_fields(ntype.params)
            for method in ntype.methods:
                if method.params:
                    resolve_fields(method.params)

    def _resolve_anonymous_types(self):
        """Create synthetic named types for anonymous inline type definitions."""
        # Process struct/union fields that have inline type dicts
        types_to_add = {}

        def process_fields(fields, parent_name):
            for i, field in enumerate(fields):
                if field.inline_type is not None:
                    synth_name = f'{parent_name}__anon_{i}'
                    prim = field.inline_type.get('primitive', 'struct')
                    cat = self._categorize_primitive(prim)
                    synth_type = NptType(
                        name=synth_name,
                        primitive=prim,
                        category=cat,
                    )
                    for j, f in enumerate(field.inline_type.get('fields', [])):
                        synth_type.fields.append(
                            _parse_field(f, parent_name=synth_name, index=j))
                    synth_type.is_anonymous = True
                    types_to_add[synth_name] = synth_type
                    self.anonymous_types.append(synth_type)
                    field.type_name = synth_name
                    field.inline_type = None

                    # Recurse into the synthetic type's fields
                    process_fields(synth_type.fields, synth_name)

        for ntype in list(self.types.values()):
            if ntype.category in (Category.STRUCT, Category.UNION) and ntype.name:
                process_fields(ntype.fields, ntype.name)

        self.types.update(types_to_add)

    # Types that are valid C primitives or known non-serializable — they
    # don't need registry entries and should not trigger warnings.
    _KNOWN_UNRESOLVED = (PRIMITIVE_NAMES | STRING_TYPES | WSTRING_TYPES |
                         NON_SERIALIZABLE_TYPES | {'wchar_t'})

    def _resolve_field_type(self, field):
        """Resolve a field's type_name to an NptType reference."""
        if not field.type_name:
            return
        field.type_ref = self.types.get(field.type_name)
        if field.type_ref is None and field.type_name not in self._KNOWN_UNRESOLVED:
            self.warn(f"Unresolved type reference: '{field.type_name}'")

    def _resolve_interface_chain(self, ntype):
        """Resolve parent chain and compute vtable indices for an interface."""
        if ntype.total_vtable_count > 0:
            return  # already resolved (or IUnknown)

        if ntype.parent_name:
            parent = self.types.get(ntype.parent_name)
            if parent:
                ntype.parent = parent
                if parent.category == Category.INTERFACE:
                    self._resolve_interface_chain(parent)
                    ntype.vtable_base = parent.total_vtable_count
                else:
                    self.warn(
                        f"Interface {ntype.name}: parent '{ntype.parent_name}' "
                        f"is {parent.category.name}, not INTERFACE")
            else:
                self.warn(f"Interface {ntype.name}: parent '{ntype.parent_name}' not found")
        # else: no parent (IUnknown itself), vtable_base stays 0

        # Assign vtable indices to methods
        for i, method in enumerate(ntype.methods):
            if method.id is not None:
                method.vtable_index = method.id
            else:
                method.vtable_index = ntype.vtable_base + i

        ntype.total_vtable_count = ntype.vtable_base + len(ntype.methods)

        # Compute family: walk up the parent chain as long as successive
        # parents share the same name base (i.e. they're version bumps of
        # the same interface, like ID3D11Device -> ID3D11Device1 -> ...).
        # Stop when the parent has a fundamentally different name.
        def _name_base(name):
            return re.sub(r'\d+$', '', name)
        root = ntype
        while (root.parent is not None and root.parent.name != 'IUnknown'
               and _name_base(root.parent.name) == _name_base(root.name)):
            root = root.parent
        ntype.family = root.name.lower()

    def get_type(self, name):
        """Look up a type by name, returns None if not found."""
        return self.types.get(name)

    def resolve_alias_chain(self, type_name):
        """Follow alias chain to the base primitive type name."""
        visited = set()
        current = type_name
        while current and current not in visited:
            visited.add(current)
            ntype = self.types.get(current)
            if ntype is None:
                return current
            if ntype.category == Category.ALIAS and ntype.alias_target:
                current = ntype.alias_target
            else:
                return current
        return current

    def is_string_type(self, field):
        """Check if a field is a null-terminated string (CHAR/char with indirection 1)."""
        if field.indirection != 1 or field.count is not None:
            return False
        # Check the field's own type name and one level of alias
        if field.type_name in STRING_TYPES:
            return True
        ntype = self.types.get(field.type_name)
        if ntype and ntype.category == Category.ALIAS and ntype.alias_target in STRING_TYPES:
            return True
        return False

    def is_wstring_type(self, field):
        """Check if a field is a null-terminated wide string (WCHAR with indirection 1)."""
        if field.indirection != 1 or field.count is not None:
            return False
        if field.type_name in WSTRING_TYPES:
            return True
        ntype = self.types.get(field.type_name)
        if ntype and ntype.category == Category.ALIAS and ntype.alias_target in WSTRING_TYPES:
            return True
        return False

    def is_interface_type(self, type_name):
        """Check if a type name refers to an interface."""
        ntype = self.types.get(type_name)
        return ntype is not None and ntype.category == Category.INTERFACE

    def field_wire_size_known(self, field):
        """
        Check if a field's wire size can be determined at code generation time.
        Returns True if the field can be encoded, False if it's unsized.
        """
        if field.is_handle:
            return True  # handles are always uint64_t
        # Non-serializable types (void, opaque OS types) — only sized when
        # used as a blob (pointer with explicit byte count)
        if field.type_name in NON_SERIALIZABLE_TYPES:
            return field.indirection >= 1 and field.count is not None
        if field.indirection == 0:
            return True  # value types have known size
        if field.count is not None:
            if isinstance(field.count, str) and parse_count_expr(field.count) is None:
                return False
            # Double pointers with a count are arrays of pointers — the
            # inner pointed-to data may have unknown size
            if field.indirection >= 2 and not field.is_handle:
                # String arrays (WCHAR** with count) are handled specially
                if field.type_name in STRING_TYPES or field.type_name in WSTRING_TYPES:
                    return True
                t = self.types.get(field.type_name)
                if t and t.category == Category.ALIAS and \
                        t.alias_target in (STRING_TYPES | WSTRING_TYPES):
                    return True
                return False
            return True  # explicit size
        if self.is_string_type(field) or self.is_wstring_type(field):
            return True  # implicit strlen/wcslen
        if self.is_interface_type(field.type_name):
            return True  # interface pointer = COM handle
        if field.indirection == 1 and field.type_name != 'void':
            # Pointer to a known type without explicit size = simple pointer
            # (encodes as presence flag + single value)
            ntype = self.types.get(field.type_name)
            if ntype and ntype.category in (
                Category.PRIMITIVE, Category.ALIAS, Category.ENUM,
                Category.STRUCT, Category.UNION,
            ):
                return True
        if field.indirection >= 1:
            return False  # void* without size, or double ptr without handle
        return True

