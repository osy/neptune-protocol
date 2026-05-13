#!/usr/bin/env python3

# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

"""
Neptune protocol code generation logic.

Generates C code strings for sizeof/encode/decode of every field type.
Used by the Mako templates via the Gen object.
"""

from typing import Optional

from npt_registry import (
    TypeRegistry, NptField, NptMethod,
    Category, PRIMITIVE_WIRE_SIZES, PRIMITIVE_NAMES,
    STRING_TYPES, WSTRING_TYPES,
    parse_count_expr,
)


# Abort lines emitted when a field cannot be serialized.  Sizeof returns 0
# (the encoded stream has no runtime marker); encode/decode set a fatal flag
# on the stream for the unsized case — the peer needs to observe the error.
_NON_SERIALIZABLE_RETURN = {
    'sizeof': ['return 0;'],
    'encode': ['return;'],
    'decode': ['return;'],
}
_UNSIZED_RETURN = {
    'sizeof': ['return 0;'],
    'encode': ['npt_cs_encoder_set_fatal(enc);', 'return;'],
    'decode': ['npt_cs_decoder_set_fatal(dec);', 'return;'],
}


class Gen:
    """
    Core code generation helper.

    Passed to Mako templates as ``GEN``.  Provides methods that return
    C code snippets for sizeof/encode/decode of individual fields.
    """

    def __init__(self, registry: TypeRegistry, is_host: bool):
        self.reg = registry
        self.is_host = is_host
        self.is_guest = not is_host
        self._context = ''  # current struct/method name for warnings

    def set_context(self, ctx: str):
        """Set the current context (struct/method name) for warning messages."""
        self._context = ctx

    # ------------------------------------------------------------------
    # Public API called from templates
    # ------------------------------------------------------------------

    def preprocess_struct_fields(self, fields):
        """
        Preprocess a struct's field list: tag bitfield members.
        Each bitfield is serialized as its own uint32_t on the wire
        (read/written via a temp variable to avoid taking its address).
        Returns a list of items where each is either an NptField or
        a tuple ('bitfield', name) for a bitfield member.
        """
        result = []
        for f in fields:
            if f.bitwidth is not None and f.name:
                result.append(('bitfield', f.name))
            else:
                result.append(f)
        return result

    def sizeof_bitfield(self, name, prefix, dst, indent=1):
        ind = '    ' * indent
        return f'{ind}{dst} += 4; /* bitfield {name} */'

    def encode_bitfield(self, name, prefix, indent=1):
        ind = '    ' * indent
        return '\n'.join([
            f'{ind}{{ uint32_t _tmp = {prefix}{name};',
            f'{ind}  npt_encode_uint32_t(enc, &_tmp); }}',
        ])

    def decode_bitfield(self, name, prefix, indent=1):
        ind = '    ' * indent
        return '\n'.join([
            f'{ind}{{ uint32_t _tmp;',
            f'{ind}  npt_decode_uint32_t(dec, &_tmp);',
            f'{ind}  {prefix}{name} = _tmp; }}',
        ])

    def sizeof_field(self, field: NptField, prefix: str, dst: str,
                     indent: int = 1, for_output: bool = False) -> str:
        """Generate sizeof statement(s) for a field. Returns C code.

        When ``for_output`` is True (reply sizing), simple pointers are
        assumed non-NULL because the host always allocates output storage.
        """
        inner = self._anonymous_inner_fields(field)
        if inner is not None:
            return '\n'.join(self.sizeof_field(f, prefix, dst, indent,
                                               for_output) for f in inner)
        lines = self._sizeof_field_impl(field, prefix, dst, for_output)
        return self._wrap_condition(field, lines, prefix, indent)

    def encode_field(self, field: NptField, prefix: str,
                     indent: int = 1, for_output: bool = False) -> str:
        """Generate encode statement(s) for a field."""
        inner = self._anonymous_inner_fields(field)
        if inner is not None:
            return '\n'.join(self.encode_field(f, prefix, indent, for_output)
                             for f in inner)
        lines = self._encode_field_impl(field, prefix, for_output)
        return self._wrap_condition(field, lines, prefix, indent)

    def decode_field(self, field: NptField, prefix: str,
                     alloc_temp: bool = True, indent: int = 1,
                     inline_storage: bool = True) -> str:
        """Generate decode statement(s) for a field.

        ``inline_storage`` controls whether fixed-size arrays at indirection 0
        should be written into inline storage (struct fields) or allocated
        from the temp pool first (command args, where ``c_type`` produces a
        pointer instead).
        """
        inner = self._anonymous_inner_fields(field)
        if inner is not None:
            return '\n'.join(self.decode_field(f, prefix, alloc_temp,
                                               indent, inline_storage)
                             for f in inner)
        lines = self._decode_field_impl(field, prefix, alloc_temp, inline_storage)
        return self._wrap_condition(field, lines, prefix, indent)

    def is_output_com_handle(self, field: NptField) -> bool:
        """
        Output-only COM handle: T ** (ID3D11Buffer **, void **, ...).

        Phase-1 refactor: these marshal as a guest-allocated uint64_t id
        in the COMMAND body (not the reply).  The host decodes the id,
        calls dxvk to obtain the real host pointer, and registers
        {guest_id -> host_ptr} in the object table.  The guest side
        treats the caller's output slot as a place to stash the
        allocated id (cast through uintptr_t) until the client thunk
        converts it to a real wrapper via npt_com_get_or_wrap.  This
        removes the reply round-trip that used to carry the host
        pointer back to the guest.
        """
        return (field.is_com_handle
                and field.indirection == 2
                and field.output
                and not field.input)

    def is_output_com_handle_array(self, field: NptField) -> bool:
        return self.is_output_com_handle(field) and field.count is not None

    def is_output_com_handle_single(self, field: NptField) -> bool:
        return self.is_output_com_handle(field) and field.count is None

    def sizeof_input_param(self, field: NptField, prefix: str, dst: str) -> str:
        """Sizeof for a command input parameter."""
        if self.is_output_com_handle(field):
            count_expr = self._get_count_expr(field, prefix)
            if count_expr:
                return (f'{dst} += sizeof(uint64_t) + (size_t)({count_expr}) '
                        f'* sizeof(uint64_t);'
                        f'  /* {field.name}: array_count + N guest ids */')
            return f'{dst} += sizeof(uint64_t);  /* {field.name}: guest id */'
        if not field.input:
            return f'/* skip {prefix}{field.name} (output only) */'
        return self.sizeof_field(field, prefix, dst)

    def encode_input_param(self, field: NptField, prefix: str) -> str:
        """Encode a command input parameter."""
        if self.is_output_com_handle(field):
            count_expr = self._get_count_expr(field, prefix)
            ptype = field.type_name
            if count_expr:
                return '\n'.join([
                    f'if ({prefix}{field.name}) {{',
                    f'    const uint64_t _cnt_{field.name} = '
                    f'(uint64_t)({count_expr});',
                    f'    npt_encode_array_count(enc, _cnt_{field.name});',
                    f'    for (uint64_t _i = 0; _i < _cnt_{field.name}; '
                    f'_i++) {{',
                    f'        const uint64_t _gid = npt_com_allocate_next_id();',
                    f'        {prefix}{field.name}[_i] = '
                    f'({ptype} *)(uintptr_t)_gid;',
                    f'        npt_encode_uint64_t(enc, &_gid);',
                    f'    }}',
                    f'}} else {{',
                    f'    npt_encode_array_count(enc, 0);',
                    f'}}',
                ])
            return '\n'.join([
                f'{{',
                f'    uint64_t _gid_{field.name} = 0;',
                f'    if ({prefix}{field.name}) {{',
                f'        _gid_{field.name} = npt_com_allocate_next_id();',
                f'        *{prefix}{field.name} = '
                f'({ptype} *)(uintptr_t)_gid_{field.name};',
                f'    }}',
                f'    npt_encode_uint64_t(enc, &_gid_{field.name});',
                f'}}',
            ])
        if not field.input:
            return f'/* skip {prefix}{field.name} (output only) */'
        return self.encode_field(field, prefix)

    def decode_input_param(self, field: NptField, prefix: str,
                           indent: int = 1) -> str:
        """Decode a command input parameter (host-side, temp alloc).
        Output-only fields are skipped — nothing is on the wire for them,
        EXCEPT output COM handles which now carry a guest-allocated id
        in the command body; we read it into a shadow field so the
        post-dispatch register pass knows which id maps to the host
        pointer dxvk fills in."""
        ind = '    ' * indent
        if self.is_output_com_handle(field):
            count_expr = self._get_count_expr(field, prefix)
            if count_expr:
                return '\n'.join([
                    f'{ind}{{',
                    f'{ind}    const uint64_t _cnt = '
                    f'npt_decode_array_count_unchecked(dec);',
                    f'{ind}    {prefix}{field.name} = '
                    f'npt_cs_decoder_alloc_temp_array(dec, sizeof(void *), '
                    f'_cnt);',
                    f'{ind}    {prefix}_guest_ids_{field.name} = _cnt ? '
                    f'npt_cs_decoder_alloc_temp_array(dec, sizeof(uint64_t), '
                    f'_cnt) : NULL;',
                    f'{ind}    {prefix}_guest_id_count_{field.name} = '
                    f'(uint32_t)_cnt;',
                    f'{ind}    if (_cnt && (!{prefix}{field.name} || '
                    f'!{prefix}_guest_ids_{field.name})) return;',
                    f'{ind}    if (_cnt) memset({prefix}{field.name}, 0, '
                    f'sizeof(void *) * _cnt);',
                    f'{ind}    for (uint64_t _i = 0; _i < _cnt; _i++) {{',
                    f'{ind}        uint64_t _gid;',
                    f'{ind}        npt_decode_uint64_t(dec, &_gid);',
                    f'{ind}        {prefix}_guest_ids_{field.name}[_i] = '
                    f'_gid;',
                    f'{ind}    }}',
                    f'{ind}}}',
                ])
            return '\n'.join([
                f'{ind}{{',
                f'{ind}    uint64_t _gid;',
                f'{ind}    npt_decode_uint64_t(dec, &_gid);',
                f'{ind}    {prefix}_guest_id_{field.name} = _gid;',
                f'{ind}    {prefix}{field.name} = '
                f'npt_cs_decoder_alloc_temp(dec, sizeof(void *));',
                f'{ind}    if (!{prefix}{field.name}) return;',
                f'{ind}    *{prefix}{field.name} = NULL;',
                f'{ind}}}',
            ])
        if not field.input:
            return ''
        return self.decode_field(field, prefix, alloc_temp=True, indent=indent,
                                 inline_storage=False)

    def alloc_output_param(self, field: NptField, prefix: str,
                           indent: int = 1) -> str:
        """Allocate temp storage for an output-only parameter.
        Called after all input params are decoded, so size fields are
        available.  Output COM handles are already allocated inside
        decode_input_param (they carry a guest_id on the wire now)."""
        if self.is_output_com_handle(field):
            return ''
        if field.input or not field.output:
            return ''
        return self._decode_output_alloc(field, prefix, indent)

    def sizeof_output_param(self, field: NptField, prefix: str, dst: str) -> str:
        """Sizeof for a reply output parameter.

        Uses for_output=True so that simple pointers are assumed non-NULL
        (the host always allocates output storage, even when the guest
        caller passed NULL for an optional param).  Output COM handles
        are registered on the host under their pre-allocated guest_id
        and do NOT ride along in the reply.
        """
        if self.is_output_com_handle(field):
            return (f'/* skip {prefix}{field.name} (guest-allocated id, '
                    f'registered host-side; not in reply) */')
        if not field.output:
            return f'/* skip {prefix}{field.name} (input only) */'
        return self.sizeof_field(field, prefix, dst, for_output=True)

    def encode_output_param(self, field: NptField, prefix: str) -> str:
        """Encode a reply output parameter (host-side)."""
        if self.is_output_com_handle(field):
            return (f'/* skip {prefix}{field.name} (guest-allocated id, '
                    f'registered host-side; not in reply) */')
        if not field.output:
            return f'/* skip {prefix}{field.name} (input only) */'
        return self.encode_field(field, prefix, for_output=True)

    def decode_output_param(self, field: NptField, prefix: str) -> str:
        """Decode a reply output parameter (guest-side)."""
        if self.is_output_com_handle(field):
            return (f'/* skip {prefix}{field.name} (guest-allocated id, '
                    f'wrapper built on client thunk; not in reply) */')
        if not field.output:
            return f'/* skip {prefix}{field.name} (input only) */'
        return self.decode_field(field, prefix, alloc_temp=False,
                                 inline_storage=False)

    # ------------------------------------------------------------------
    # Type name helpers
    # ------------------------------------------------------------------

    def c_type(self, field: NptField, force_const: bool = False) -> str:
        """C type string for a field (e.g. 'const D3D12_COMMAND_QUEUE_DESC *').

        When *force_const* is True the pointed-to type is const-qualified
        even if the field itself is not marked const.  This is used for
        sizeof function signatures where the argument is never modified.
        Double-pointer types (indirection >= 2) are excluded because
        ``const T **`` is not implicitly convertible from ``T **`` in C.
        """
        parts = []
        indirection = field.indirection
        # Fixed-size arrays at indirection 0 are passed as pointers
        if indirection == 0 and field.is_fixed_array:
            indirection = 1
        if field.const or (force_const and indirection <= 1):
            parts.append('const')
        parts.append(field.type_name if field.type_name else 'void')
        result = ' '.join(parts)
        result += ' ' + '*' * indirection
        return result.strip()

    # ------------------------------------------------------------------
    # Return type helpers (used by templates via GEN)
    # ------------------------------------------------------------------

    def has_return(self, ret_type):
        """True if the return type is non-void."""
        return ret_type not in {'VOID', 'void', None, ''}

    def is_scalar_return(self, ret_type):
        """True if the return type fits in cmd_return (uint32_t).

        Resolves aliases and checks wire size instead of matching names."""
        if not self.has_return(ret_type):
            return False
        ref = self.reg.get_type(ret_type)
        if ref and ref.category == Category.ENUM:
            return True
        base = self.reg.resolve_alias_chain(ret_type)
        wire = PRIMITIVE_WIRE_SIZES.get(base)
        return wire is not None and wire <= 4

    def ret_type_str(self, ret_type):
        """C return type string ('void' for void-typed methods)."""
        return ret_type if self.has_return(ret_type) else 'void'

    # ------------------------------------------------------------------
    # Internal: field classification
    # ------------------------------------------------------------------

    def _string_array_info(self, field):
        """Check if field is a string array (WCHAR/CHAR at indirection 2 with count).
        Returns (is_string_array, is_wide).
        Checks the type name directly first, then one level of alias."""
        if field.indirection != 2 or field.count is None:
            return False, False
        if field.type_name in WSTRING_TYPES:
            return True, True
        if field.type_name in STRING_TYPES:
            return True, False
        ntype = self.reg.types.get(field.type_name)
        if ntype and ntype.category == Category.ALIAS:
            if ntype.alias_target in WSTRING_TYPES:
                return True, True
            if ntype.alias_target in STRING_TYPES:
                return True, False
        return False, False

    @staticmethod
    def _anonymous_inner_fields(field):
        """Return inner fields if this is an unnamed struct/union to flatten, else None."""
        if (field.name is None and field.type_ref is not None
                and field.type_ref.category in (Category.STRUCT, Category.UNION)):
            return field.type_ref.fields
        return None

    @staticmethod
    def _acc(field, prefix):
        """C accessor expression for a field (e.g. 'val->Foo' or 'val')."""
        return f'{prefix}{field.name}' if field.name else prefix.rstrip('.')

    @staticmethod
    def _resolve_size_term(term, prefix, deref, optional=False):
        """Resolve a single term in a size expression to a C expression.
        term is one of: "FieldName", "FieldName->Member", "sizeof(TYPE)", or a number.
        prefix is e.g. "val->" or "" (for command params).
        deref is the number of pointer dereferences needed for the base field.
        optional, when True with deref>=1, wraps the deref in a NULL guard so
        a nullable count pointer (e.g. PSGetShader's pNumClassInstances) does
        not crash sizing/encoding paths.
        """
        term = term.strip()
        if term.isdigit():
            return term
        if term.startswith('sizeof('):
            return term  # pass through to the C compiler
        if '->' in term:
            # "pDesc->MipLevels" — the -> already dereferences the pointer,
            # so no additional deref is needed. Just prefix the base field name.
            parts = term.split('->', 1)
            return f'{prefix}{parts[0]}->{parts[1]}'
        # Simple field name — apply dereferences based on the field's indirection.
        # deref == -1 means global constant (not a sibling field) — don't prefix.
        if deref < 0:
            return term
        if deref >= 1 and optional:
            return f'({prefix}{term} ? *{prefix}{term} : 0)'
        return f'{"*" * deref}{prefix}{term}'

    def _get_count_expr(self, field, prefix):
        """Get the C expression for the array count of a pointer field.
        Returns the expression string, or None if the count is unknown."""
        size = field.count
        if size is None:
            return None

        if isinstance(size, int):
            return str(size)

        if isinstance(size, list):
            return ' * '.join(str(d) for d in size)

        if isinstance(size, str):
            parsed = parse_count_expr(size)
            if parsed is None:
                return None
            # Numeric literal
            if parsed.isdigit():
                return parsed
            # Split on '*' for multiplication
            terms = [t.strip() for t in parsed.split('*')]
            deref = field._size_deref
            optional = field._size_optional
            c_terms = [self._resolve_size_term(t, prefix, deref, optional)
                       for t in terms]
            return ' * '.join(c_terms)

        return None

    def _get_output_count_expr(self, field, prefix):
        """Get the output count expression from the count_output field."""
        if field.count_output:
            deref = field._size_output_deref
            if deref < 0:
                return field.count_output
            if deref >= 1 and field._size_output_optional:
                return (f'({prefix}{field.count_output} ? '
                        f'*{prefix}{field.count_output} : 0)')
            return f'{"*" * deref}{prefix}{field.count_output}'
        return self._get_count_expr(field, prefix)

    # ------------------------------------------------------------------
    # Internal: shared validation gates for the three-pass dispatch
    # ------------------------------------------------------------------

    def _non_serializable_err(self, field, op):
        """Emit the non-serializable skip or error block for ``op``."""
        if field.optional:
            return [f'/* {field.name}: non-serializable, skipped */']
        return [f'/* ERROR: {field.name} ({field.type_name}) is not serializable */',
                *_NON_SERIALIZABLE_RETURN[op]]

    def _unsized_err(self, field, op, *, dst=None, acc=None):
        """Emit the unsized-optional fallback or unsized-required error for ``op``.

        Sizeof is the canonical warn site — encode/decode see the same
        field later and would just echo the same warning, so they stay silent.
        """
        if field.optional:
            if op == 'sizeof':
                return [f'/* {field.name}: unsized optional, always NULL */',
                        f'{dst} += npt_sizeof_array_count(0);']
            if op == 'encode':
                return [f'/* {field.name}: unsized optional, encode NULL */',
                        f'npt_encode_array_count(enc, 0);']
            return [f'/* {field.name}: unsized optional, skip */',
                    f'(void)npt_decode_array_count_unchecked(dec);',
                    f'(void){acc};']
        if op == 'sizeof':
            ctx = f" in {self._context}" if self._context else ""
            self.reg.warn(
                f"Field '{field.name}' (type={field.type_name}, "
                f"indirection={field.indirection}) has no determinable size{ctx}")
        return [f'/* ERROR: {field.name} is unsized and not optional */',
                *_UNSIZED_RETURN[op]]

    def _unmatched_warn(self, field, op):
        """Warn and emit a TODO for a field that fell through every dispatch case."""
        self.reg.warn(f"Field '{field.name}' (type={field.type_name}) did not match "
                      f"any {op} pattern in {self._context}")
        return [f'/* TODO: {op} {field.name} */']

    # ------------------------------------------------------------------
    # Internal: sizeof generation
    # ------------------------------------------------------------------

    def _sizeof_field_impl(self, field, prefix, dst, for_output=False):
        acc = self._acc(field, prefix)

        # Non-serializable value types (void* with size is a blob, not this)
        if field.is_non_serializable:
            return self._non_serializable_err(field, 'sizeof')

        # Handle annotations — all cases (single, array, COM, Win32)
        if field.is_handle:
            return self._sizeof_handle(field, prefix, dst)

        # Interface reference without explicit handle annotation
        if field.indirection >= 1 and self.reg.is_interface_type(field.type_name):
            return [f'{dst} += sizeof(uint64_t);']

        # Fixed-size embedded array (indirection=0 but has size) —
        # serialized as a pointer per the wire format spec
        if field.indirection == 0 and field.is_fixed_array:
            return self._sizeof_pointer(field, acc, prefix, dst, for_output)

        # Indirection 0: value types
        if field.indirection == 0:
            return self._sizeof_value(field, acc, dst)

        # Array of strings (WCHAR** or CHAR** with count)
        is_str_arr, is_wide = self._string_array_info(field)
        if is_str_arr:
            return self._sizeof_string_array(field, acc, prefix, dst, is_wide)

        if not self.reg.field_wire_size_known(field):
            return self._unsized_err(field, 'sizeof', dst=dst)

        # String types
        if self.reg.is_string_type(field) or self.reg.is_wstring_type(field):
            return self._sizeof_string(field, acc, dst)

        # Blob pointer (void* with size)
        if field.is_blob:
            return self._sizeof_blob(field, acc, prefix, dst)

        # Pointer to array/value
        if field.indirection >= 1:
            return self._sizeof_pointer(field, acc, prefix, dst, for_output)

        return self._unmatched_warn(field, 'sizeof')

    def _sizeof_handle(self, field, prefix, dst):
        """Sizeof for any handle field (single or array, COM or Win32)."""
        if field.indirection >= 2 and field.count:
            count_expr = self._get_count_expr(field, prefix)
            return [f'{dst} += npt_sizeof_array_count({count_expr});',
                    f'{dst} += sizeof(uint64_t) * {count_expr};']
        return [f'{dst} += sizeof(uint64_t);']

    def _sizeof_value(self, field, acc, dst):
        """Sizeof for a value type (indirection=0)."""
        if field.is_anonymous_type:
            return [f'{dst} += npt_sizeof_{field.type_name}((const {field.type_name} *)&{acc});']
        return [f'{dst} += npt_sizeof_{field.type_name}(&{acc});']

    @staticmethod
    def _strlen_expr(accessor, is_wide):
        """C expression for the byte length of a null-terminated string."""
        if is_wide:
            return f'(npt_wcslen((const WCHAR *){accessor}) + 1) * sizeof(WCHAR)'
        return f'strlen((const char *){accessor}) + 1'

    def _sizeof_string(self, field, acc, dst):
        is_wide = self.reg.is_wstring_type(field)
        var = '_wstr_size' if is_wide else '_str_size'
        len_expr = self._strlen_expr(acc, is_wide)
        return [
            f'if ({acc}) {{',
            f'    const size_t {var} = {len_expr};',
            f'    {dst} += npt_sizeof_array_count({var});',
            f'    {dst} += npt_sizeof_blob_array({acc}, {var});',
            f'}} else {{',
            f'    {dst} += npt_sizeof_array_count(0);',
            f'}}',
        ]

    def _sizeof_string_array(self, field, acc, prefix, dst, is_wide):
        """Sizeof for an array of string pointers (WCHAR** or CHAR**)."""
        count_expr = self._get_count_expr(field, prefix)
        strlen_fn = self._strlen_expr(f'{acc}[_i]', is_wide)
        return [
            f'{dst} += npt_sizeof_array_count({acc} ? {count_expr} : 0);',
            f'for (uint64_t _i = 0; _i < ({acc} ? (uint64_t){count_expr} : 0); _i++) {{',
            f'    const size_t _slen = {acc}[_i] ? {strlen_fn} : 0;',
            f'    {dst} += npt_sizeof_array_count(_slen);',
            f'    {dst} += npt_sizeof_blob_array({acc}[_i], _slen);',
            f'}}',
        ]

    def _sizeof_blob(self, field, acc, prefix, dst):
        # Always use the input count (capacity) for sizing — the output
        # count may reference a field not yet written (e.g. guest pre-
        # allocating the reply buffer before the host call).
        count_expr = self._get_count_expr(field, prefix)
        if count_expr is None:
            # Inexpressible count (e.g. D3D12_PIPELINE_STATE_STREAM_DESC's
            # pPipelineStateSubobjectStream).  Fall back to 0 — callers
            # that need this blob must provide an override.
            count_expr = '0'
        return [
            f'if ({acc}) {{',
            f'    {dst} += npt_sizeof_array_count({count_expr});',
            f'    {dst} += npt_sizeof_blob_array({acc}, {count_expr});',
            f'}} else {{',
            f'    {dst} += npt_sizeof_array_count(0);',
            f'}}',
        ]

    def _sizeof_pointer(self, field, acc, prefix, dst, for_output=False):
        """Sizeof for a pointer to typed data."""
        # Always use the input count (capacity) for sizing — the output
        # count may reference a field not yet written by the host.
        count_expr = self._get_count_expr(field, prefix)

        # T**+count where T is a struct/union: array of N pointers, each
        # dereferenced to a single inner struct.  acc[_i] is already T*,
        # so pass it directly to npt_sizeof_<T> (no `&`).
        if field.indirection >= 2 and count_expr is not None and not field.is_handle:
            return [
                f'{dst} += npt_sizeof_array_count({acc} ? {count_expr} : 0);',
                f'for (uint32_t _i = 0; _i < ({acc} ? {count_expr} : 0); _i++)',
                f'    {dst} += npt_sizeof_{field.type_name}({acc}[_i]);',
            ]

        if count_expr is None:
            if for_output:
                # Output simple pointer: host always allocates, so the
                # reply always includes the presence flag + data, even if
                # the guest caller passed NULL for an optional param.
                # void has no compound-literal form, so use NULL as the
                # dummy argument (npt_sizeof_void ignores it anyway).
                if field.type_name == 'void':
                    sizeof_arg = 'NULL'
                else:
                    sizeof_arg = f'&(const {field.type_name}){{0}}'
                return [
                    f'{dst} += npt_sizeof_simple_pointer((const void *)1);',
                    f'{dst} += npt_sizeof_{field.type_name}({sizeof_arg});',
                ]
            # Simple pointer (single value)
            return [
                f'{dst} += npt_sizeof_simple_pointer({acc});',
                f'if ({acc})',
                f'    {dst} += npt_sizeof_{field.type_name}({acc});',
            ]

        fixed = field.is_fixed_array
        base = self.reg.resolve_alias_chain(field.type_name)

        if base in PRIMITIVE_NAMES or field.is_enum:
            if fixed:
                return [
                    f'{dst} += npt_sizeof_array_count({count_expr});',
                    f'{dst} += npt_sizeof_{field.type_name}_array((const {field.type_name} *){acc}, {count_expr});',
                ]
            return [
                f'{dst} += npt_sizeof_array_count({acc} ? {count_expr} : 0);',
                f'if ({acc})',
                f'    {dst} += npt_sizeof_{field.type_name}_array({acc}, {count_expr});',
            ]
        else:
            if fixed:
                return [
                    f'{dst} += npt_sizeof_array_count({count_expr});',
                    f'for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                    f'    {dst} += npt_sizeof_{field.type_name}(&{acc}[_i]);',
                ]
            return [
                f'{dst} += npt_sizeof_array_count({acc} ? {count_expr} : 0);',
                f'for (uint32_t _i = 0; _i < ({acc} ? {count_expr} : 0); _i++)',
                f'    {dst} += npt_sizeof_{field.type_name}(&{acc}[_i]);',
            ]

    # ------------------------------------------------------------------
    # Internal: encode generation
    # ------------------------------------------------------------------

    def _encode_field_impl(self, field, prefix, for_output=False):
        acc = self._acc(field, prefix)

        if field.is_non_serializable:
            return self._non_serializable_err(field, 'encode')

        # Handle annotations — _encode_handle dispatches all cases internally
        # (single, array, input, output) so no exclusion guard is needed here
        if field.is_handle:
            return self._encode_handle(field, acc, prefix)

        # Interface reference without explicit handle annotation
        if field.indirection >= 1 and self.reg.is_interface_type(field.type_name):
            return [f'npt_encode_com_handle(enc, npt_object_get_id({acc}));']

        # Fixed-size embedded array
        if field.indirection == 0 and field.is_fixed_array:
            return self._encode_pointer(field, acc, prefix, for_output)

        if field.indirection == 0:
            return self._encode_value(field, acc)

        is_str_arr, is_wide = self._string_array_info(field)
        if is_str_arr:
            return self._encode_string_array(field, acc, prefix, is_wide)

        if not self.reg.field_wire_size_known(field):
            return self._unsized_err(field, 'encode')

        if self.reg.is_string_type(field) or self.reg.is_wstring_type(field):
            return self._encode_string(field, acc)

        if field.is_blob:
            return self._encode_blob(field, acc, prefix, for_output)

        if field.indirection >= 1:
            return self._encode_pointer(field, acc, prefix, for_output)

        return self._unmatched_warn(field, 'encode')

    def _encode_value(self, field, acc):
        if field.is_anonymous_type:
            return [f'npt_encode_{field.type_name}(enc, (const {field.type_name} *)&{acc});']
        return [f'npt_encode_{field.type_name}(enc, &{acc});']

    def _encode_handle(self, field, acc, prefix):
        if field.is_com_handle:
            if field.indirection == 2 and field.output:
                return self._encode_output_com_handle(field, acc, prefix)
            if field.indirection >= 2 and field.count:
                # Input array of COM handles
                count_expr = self._get_count_expr(field, prefix)
                return [
                    f'if ({acc}) {{',
                    f'    npt_encode_array_count(enc, {count_expr});',
                    f'    for (uint32_t _i = 0; _i < (uint32_t){count_expr}; _i++)',
                    f'        npt_encode_com_handle(enc, npt_object_get_id({acc}[_i]));',
                    f'}} else {{',
                    f'    npt_encode_array_count(enc, 0);',
                    f'}}',
                ]
            if field.indirection >= 1:
                # Pointer field: pass the handle pointer directly to the mapping
                return [f'npt_encode_com_handle(enc, npt_object_get_id({acc}));']
            else:
                # Value-type COM handle: cast through uintptr_t to a void *
                return [f'npt_encode_com_handle(enc, npt_object_get_id((const void *)(uintptr_t){acc}));']
        elif field.is_win32_handle:
            if field.indirection >= 1:
                # Pointer to handle: dereference to get the handle value
                return [f'npt_encode_win32_handle(enc, npt_win32_handle_get_id((const void *)(uintptr_t)*{acc}));']
            else:
                # Value-type Win32 handle: cast through uintptr_t to a void *
                return [f'npt_encode_win32_handle(enc, npt_win32_handle_get_id((const void *)(uintptr_t){acc}));']
        return [f'/* unknown handle type for {field.name} */']

    def _encode_output_com_handle(self, field, acc, prefix=''):
        count_expr = self._get_count_expr(field, prefix)
        if count_expr:
            # Array of COM handle outputs
            return [
                f'if ({acc}) {{',
                f'    npt_encode_array_count(enc, {count_expr});',
                f'    for (uint32_t _i = 0; _i < (uint32_t){count_expr}; _i++) {{',
                f'        npt_object_id _out_id = {acc}[_i]',
                f'            ? npt_object_get_id({acc}[_i]) : 0;',
                f'        npt_encode_uint64_t(enc, &_out_id);',
                f'    }}',
                f'}} else {{',
                f'    npt_encode_array_count(enc, 0);',
                f'}}',
            ]
        return [
            f'{{',
            f'    npt_object_id _out_id = ({acc} && *{acc})',
            f'        ? npt_object_get_id(*{acc}) : 0;',
            f'    npt_encode_uint64_t(enc, &_out_id);',
            f'}}',
        ]

    def _encode_string(self, field, acc):
        is_wide = self.reg.is_wstring_type(field)
        var = '_wstr_size' if is_wide else '_str_size'
        len_expr = self._strlen_expr(acc, is_wide)
        return [
            f'if ({acc}) {{',
            f'    const size_t {var} = {len_expr};',
            f'    npt_encode_array_count(enc, {var});',
            f'    npt_encode_blob_array(enc, {acc}, {var});',
            f'}} else {{',
            f'    npt_encode_array_count(enc, 0);',
            f'}}',
        ]

    def _encode_string_array(self, field, acc, prefix, is_wide):
        count_expr = self._get_count_expr(field, prefix)
        strlen_fn = self._strlen_expr(f'{acc}[_i]', is_wide)
        return [
            f'if ({acc}) {{',
            f'    npt_encode_array_count(enc, {count_expr});',
            f'    for (uint64_t _i = 0; _i < (uint64_t){count_expr}; _i++) {{',
            f'        const size_t _slen = {acc}[_i] ? {strlen_fn} : 0;',
            f'        npt_encode_array_count(enc, _slen);',
            f'        npt_encode_blob_array(enc, {acc}[_i], _slen);',
            f'    }}',
            f'}} else {{',
            f'    npt_encode_array_count(enc, 0);',
            f'}}',
        ]

    def _encode_blob(self, field, acc, prefix, for_output=False):
        if for_output:
            count_expr = self._get_output_count_expr(field, prefix)
        else:
            count_expr = self._get_count_expr(field, prefix)
        if count_expr is None:
            count_expr = '0'
        return [
            f'if ({acc}) {{',
            f'    npt_encode_array_count(enc, {count_expr});',
            f'    npt_encode_blob_array(enc, {acc}, {count_expr});',
            f'}} else {{',
            f'    npt_encode_array_count(enc, 0);',
            f'}}',
        ]

    def _encode_pointer(self, field, acc, prefix, for_output=False):
        if for_output:
            count_expr = self._get_output_count_expr(field, prefix)
        else:
            count_expr = self._get_count_expr(field, prefix)

        # T**+count where T is a struct/union: array of N pointers, each
        # dereferenced to a single inner struct.  acc[_i] is T*; pass it
        # directly to npt_encode_<T> (no `&`).
        if field.indirection >= 2 and count_expr is not None and not field.is_handle:
            return [
                f'if ({acc}) {{',
                f'    npt_encode_array_count(enc, {count_expr});',
                f'    for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                f'        npt_encode_{field.type_name}(enc, {acc}[_i]);',
                f'}} else {{',
                f'    npt_encode_array_count(enc, 0);',
                f'}}',
            ]

        if count_expr is None:
            return [
                f'if (npt_encode_simple_pointer(enc, {acc}))',
                f'    npt_encode_{field.type_name}(enc, {acc});',
            ]

        fixed = field.is_fixed_array
        base = self.reg.resolve_alias_chain(field.type_name)

        if base in PRIMITIVE_NAMES or field.is_enum:
            if fixed:
                return [
                    f'npt_encode_array_count(enc, {count_expr});',
                    f'npt_encode_{field.type_name}_array(enc, (const {field.type_name} *){acc}, {count_expr});',
                ]
            return [
                f'if ({acc}) {{',
                f'    npt_encode_array_count(enc, {count_expr});',
                f'    npt_encode_{field.type_name}_array(enc, {acc}, {count_expr});',
                f'}} else {{',
                f'    npt_encode_array_count(enc, 0);',
                f'}}',
            ]
        else:
            if fixed:
                return [
                    f'npt_encode_array_count(enc, {count_expr});',
                    f'for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                    f'    npt_encode_{field.type_name}(enc, &{acc}[_i]);',
                ]
            return [
                f'if ({acc}) {{',
                f'    npt_encode_array_count(enc, {count_expr});',
                f'    for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                f'        npt_encode_{field.type_name}(enc, &{acc}[_i]);',
                f'}} else {{',
                f'    npt_encode_array_count(enc, 0);',
                f'}}',
            ]

    # ------------------------------------------------------------------
    # Internal: decode generation
    # ------------------------------------------------------------------

    def _decode_field_impl(self, field, prefix, alloc_temp, inline_storage=True):
        acc = self._acc(field, prefix)

        if field.is_non_serializable:
            return self._non_serializable_err(field, 'decode')

        # Handle annotations — COM handles handle all cases (single, double-ptr,
        # array); Win32 handle arrays fall through to the unsized check.
        if field.is_handle and (field.is_com_handle
                                or not (field.indirection >= 2 and field.count)):
            return self._decode_handle(field, acc, prefix, alloc_temp)

        if field.indirection >= 1 and self.reg.is_interface_type(field.type_name):
            return [f'npt_decode_com_handle(dec, (npt_object_id *)&{acc});']

        # Fixed-size embedded array
        if field.indirection == 0 and field.is_fixed_array:
            return self._decode_fixed_array(field, acc, prefix, inline_storage)

        if field.indirection == 0:
            return self._decode_value(field, acc)

        is_str_arr, is_wide = self._string_array_info(field)
        if is_str_arr:
            return self._decode_string_array(field, acc, prefix, alloc_temp, is_wide)

        if not self.reg.field_wire_size_known(field):
            return self._unsized_err(field, 'decode', acc=acc)

        if self.reg.is_string_type(field) or self.reg.is_wstring_type(field):
            return self._decode_string(field, acc, alloc_temp)

        if field.is_blob:
            return self._decode_blob(field, acc, alloc_temp)

        if field.indirection >= 1:
            return self._decode_pointer(field, acc, prefix, alloc_temp)

        return self._unmatched_warn(field, 'decode')

    def _decode_value(self, field, acc):
        if field.is_anonymous_type:
            return [f'npt_decode_{field.type_name}(dec, ({field.type_name} *)&{acc});']
        return [f'npt_decode_{field.type_name}(dec, &{acc});']

    @staticmethod
    def _decode_id_block(body_lines, var='_id'):
        """Emit ``{ npt_object_id <var>; npt_decode_uint64_t(dec, &<var>); <body> }``."""
        return [
            '{',
            f'    npt_object_id {var};',
            f'    npt_decode_uint64_t(dec, &{var});',
            *[f'    {line}' for line in body_lines],
            '}',
        ]

    def _decode_handle(self, field, acc, prefix, alloc_temp):
        if field.is_com_handle:
            if field.indirection == 2:
                # Both input and output arrays go through the COM handle path
                return self._decode_output_com_handle(field, acc, alloc_temp, prefix)
            if field.indirection >= 1:
                # Input pointer handle: decode wire ID and convert via project
                # hook. On host (alloc_temp=True), acc is `args->Foo`. The
                # host's npt_object_from_id is a no-op cast so the raw ID
                # stays in the field for the replace pass to convert later.
                # On guest (alloc_temp=False), this path is unreachable for
                # input handles since decode_output_param skips them.
                return self._decode_id_block(
                    [f'{acc} = ({field.type_name} *)npt_object_from_id(_id);'])
            # Value-type COM handle: same convert-via-hook pattern
            return self._decode_id_block(
                [f'{acc} = ({field.type_name})(uintptr_t)npt_object_from_id(_id);'])
        elif field.is_win32_handle:
            if field.indirection >= 1 and field.output:
                # Output handle pointer: decode into *pHandle via project hook.
                return self._decode_id_block([
                    f'if ({acc})',
                    f'    *{acc} = ({field.type_name})(uintptr_t)npt_win32_handle_from_id(_id);',
                ])
            if field.indirection >= 1:
                # Input pointer to win32 handle (rare): decode wire ID into
                # the pointer storage. Host's replace pass converts later.
                return [f'npt_decode_win32_handle(dec, (npt_object_id *)&{acc});']
            # Value-type Win32 handle: same convert-via-hook pattern.
            return self._decode_id_block(
                [f'{acc} = ({field.type_name})(uintptr_t)npt_win32_handle_from_id(_id);'])
        return [f'/* unknown handle type for {field.name} */']

    def _decode_output_com_handle(self, field, acc, alloc_temp, prefix=''):
        """Decode for a double-pointer COM handle (void** or Interface**).

        Despite the name, this is also reached for INPUT arrays of COM
        handles (e.g., ID3D11DeviceContext::OMSetRenderTargets's
        ppRenderTargetViews). For inputs we must consume the handle IDs
        from the wire; for outputs we just allocate empty slots and let the
        underlying COM call fill them in.
        """
        count_expr = self._get_count_expr(field, prefix)
        if alloc_temp:
            if count_expr:
                # Array of COM handle pointers
                if field.input:
                    # INPUT array — wire format: array_count, then N handle ids.
                    # Encoder writes 0 when the input pointer is NULL.
                    return [
                        f'{{',
                        f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                        f'    if (_count) {{',
                        f'        {acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof(void *), _count);',
                        f'        if (!{acc}) return;',
                        f'        for (uint64_t _i = 0; _i < _count; _i++) {{',
                        f'            npt_object_id _id;',
                        f'            npt_decode_uint64_t(dec, &_id);',
                        f'            {acc}[_i] = npt_object_from_id(_id);',
                        f'        }}',
                        f'    }} else {{',
                        f'        {acc} = NULL;',
                        f'    }}',
                        f'}}',
                    ]
                # OUTPUT-only array — alloc empty slots for the COM call to fill
                return [
                    f'if ({count_expr}) {{',
                    f'    {acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof(void *), {count_expr});',
                    f'    if (!{acc}) return;',
                    f'    memset({acc}, 0, sizeof(void *) * {count_expr});',
                    f'}} else {{',
                    f'    {acc} = NULL;',
                    f'}}',
                ]
            # Single double-pointer COM handle (e.g., ppDevice).
            # Almost always output-only, but if it's marked input the wire
            # would carry one ID — handle that case too.
            if field.input:
                return [
                    f'{acc} = npt_cs_decoder_alloc_temp(dec, sizeof(void *));',
                    f'if (!{acc}) return;',
                    *self._decode_id_block([f'*{acc} = npt_object_from_id(_id);']),
                ]
            return [
                f'{acc} = npt_cs_decoder_alloc_temp(dec, sizeof(void *));',
                f'if (!{acc}) return;',
                f'*{acc} = NULL;',
            ]
        # Guest-side reply decode
        if count_expr:
            return [
                f'{{',
                f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                f'    for (uint64_t _i = 0; _i < _count && {acc}; _i++) {{',
                f'        npt_object_id _out_id;',
                f'        npt_decode_uint64_t(dec, &_out_id);',
                f'        {acc}[_i] = npt_object_from_id(_out_id);',
                f'    }}',
                f'}}',
            ]
        return self._decode_id_block([
            f'if ({acc})',
            f'    *{acc} = npt_object_from_id(_out_id);',
        ], var='_out_id')

    @staticmethod
    def _decode_contiguous(acc, alloc_temp, var, decode_fn, cast):
        """Decode a contiguous byte sequence (string, wstring, or blob)."""
        if alloc_temp:
            return [
                f'{{',
                f'    const uint64_t {var} = npt_decode_array_count_unchecked(dec);',
                f'    if ({var}) {{',
                f'        {acc} = npt_cs_decoder_alloc_temp(dec, {var});',
                f'        if (!{acc}) return;',
                f'        {decode_fn}(dec, {cast}{acc}, {var});',
                f'    }} else {{',
                f'        {acc} = NULL;',
                f'    }}',
                f'}}',
            ]
        return [
            f'{{',
            f'    const uint64_t {var} = npt_decode_array_count_unchecked(dec);',
            f'    if ({var} && {acc})',
            f'        {decode_fn}(dec, {cast}{acc}, {var});',
            f'    else if ({var})',
            f'        npt_cs_decoder_read(dec, (({var} + 3) & ~3), NULL, 0);',
            f'}}',
        ]

    def _decode_string(self, field, acc, alloc_temp):
        if self.reg.is_wstring_type(field):
            return self._decode_contiguous(acc, alloc_temp,
                '_wstr_size', 'npt_decode_wchar_array', '(WCHAR *)')
        return self._decode_contiguous(acc, alloc_temp,
            '_str_size', 'npt_decode_char_array', '(char *)')

    def _decode_blob(self, field, acc, alloc_temp):
        return self._decode_contiguous(acc, alloc_temp,
            '_blob_size', 'npt_decode_blob_array', '(void *)')

    def _decode_string_array(self, field, acc, prefix, alloc_temp, is_wide):
        decode_fn = 'npt_decode_wchar_array' if is_wide else 'npt_decode_blob_array'
        cast = '(WCHAR *)' if is_wide else '(void *)'
        if alloc_temp:
            return [
                f'{{',
                f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                f'    if (_count) {{',
                f'        {acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof(void *), _count);',
                f'        if (!{acc}) return;',
                f'        for (uint64_t _i = 0; _i < _count; _i++) {{',
                f'            const uint64_t _slen = npt_decode_array_count_unchecked(dec);',
                f'            if (_slen) {{',
                f'                {acc}[_i] = npt_cs_decoder_alloc_temp(dec, _slen);',
                f'                if (!{acc}[_i]) return;',
                f'                {decode_fn}(dec, {cast}{acc}[_i], _slen);',
                f'            }} else {{',
                f'                {acc}[_i] = NULL;',
                f'            }}',
                f'        }}',
                f'    }} else {{',
                f'        {acc} = NULL;',
                f'    }}',
                f'}}',
            ]
        else:
            return [
                f'{{',
                f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                f'    for (uint64_t _i = 0; _i < _count && {acc}; _i++) {{',
                f'        const uint64_t _slen = npt_decode_array_count_unchecked(dec);',
                f'        if (_slen && {acc}[_i])',
                f'            {decode_fn}(dec, {cast}{acc}[_i], _slen);',
                f'        else if (_slen)',
                f'            npt_cs_decoder_read(dec, ((_slen + 3) & ~3), NULL, 0);',
                f'    }}',
                f'}}',
            ]

    def _decode_pointer(self, field, acc, prefix, alloc_temp):
        count_expr = self._get_count_expr(field, prefix)

        # T**+count where T is a struct/union: allocate N inner-pointer
        # slots, then allocate one inner struct per slot and decode into it.
        # acc is the T** field; each acc[i] ends up as a T*.  Only the
        # host-side (alloc_temp=True) path is supported — output T** with
        # count doesn't occur in the registry today.
        if field.indirection >= 2 and count_expr is not None and not field.is_handle \
                and alloc_temp:
            return [
                f'if (npt_peek_array_count(dec)) {{',
                f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                f'    {acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof({field.type_name} *), _count);',
                f'    if (!{acc}) return;',
                f'    for (uint32_t _i = 0; _i < (uint32_t)_count; _i++) {{',
                f'        {field.type_name} *_elem = npt_cs_decoder_alloc_temp(dec, sizeof({field.type_name}));',
                f'        if (!_elem) return;',
                f'        npt_decode_{field.type_name}(dec, _elem);',
                f'        (({field.type_name} **){acc})[_i] = _elem;',
                f'    }}',
                f'}} else {{',
                f'    (void)npt_decode_array_count_unchecked(dec); /* consume the 0 */',
                f'    (void)({count_expr}); /* unused: count_expr from registry */',
                f'    {acc} = NULL;',
                f'}}',
            ]

        if count_expr is None:
            # Simple pointer (no size at all) — uses presence prefix
            if alloc_temp:
                null_lines = [f'    {acc} = NULL;']
                if not field.optional:
                    null_lines.append(f'    npt_cs_decoder_set_fatal(dec); /* non-optional pointer is NULL */')
                return [
                    f'if (npt_decode_simple_pointer(dec)) {{',
                    f'    {acc} = npt_cs_decoder_alloc_temp(dec, sizeof({field.type_name}));',
                    f'    if (!{acc}) return;',
                    f'    npt_decode_{field.type_name}(dec, ({field.type_name} *){acc});',
                    f'}} else {{',
                    *null_lines,
                    f'}}',
                ]
            else:
                return [
                    f'if (npt_decode_simple_pointer(dec)) {{',
                    f'    if ({acc})',
                    f'        npt_decode_{field.type_name}(dec, ({field.type_name} *){acc});',
                    f'}}',
                ]

        base = self.reg.resolve_alias_chain(field.type_name)
        if alloc_temp:
            # Optional array: encoder writes count=0 for NULL pointers, count=N
            # for non-NULL.  We don't validate the count against the
            # registry's count_expr because callers may legitimately pass NULL
            # even when the descriptor says non-zero (e.g., D3D11 textures
            # with no initial data).
            if base in PRIMITIVE_NAMES or field.is_enum:
                return [
                    f'if (npt_peek_array_count(dec)) {{',
                    f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                    f'    {acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof({field.type_name}), _count);',
                    f'    if (!{acc}) return;',
                    f'    npt_decode_{field.type_name}_array(dec, ({field.type_name} *){acc}, _count);',
                    f'}} else {{',
                    f'    (void)npt_decode_array_count_unchecked(dec); /* consume the 0 */',
                    f'    (void)({count_expr}); /* unused: count_expr from registry */',
                    f'    {acc} = NULL;',
                    f'}}',
                ]
            else:
                return [
                    f'if (npt_peek_array_count(dec)) {{',
                    f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                    f'    {acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof({field.type_name}), _count);',
                    f'    if (!{acc}) return;',
                    f'    for (uint32_t _i = 0; _i < (uint32_t)_count; _i++)',
                    f'        npt_decode_{field.type_name}(dec, ({field.type_name} *)&{acc}[_i]);',
                    f'}} else {{',
                    f'    (void)npt_decode_array_count_unchecked(dec); /* consume the 0 */',
                    f'    (void)({count_expr}); /* unused: count_expr from registry */',
                    f'    {acc} = NULL;',
                    f'}}',
                ]
        else:
            if base in PRIMITIVE_NAMES or field.is_enum:
                return [
                    f'{{',
                    f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                    f'    if (_count && {acc})',
                    f'        npt_decode_{field.type_name}_array(dec, ({field.type_name} *){acc}, _count);',
                    f'    else if (_count)',
                    f'        npt_cs_decoder_set_fatal(dec); /* data sent but no buffer */  ',
                    f'}}',
                ]
            else:
                return [
                    f'{{',
                    f'    const uint64_t _count = npt_decode_array_count_unchecked(dec);',
                    f'    if (_count && {acc}) {{',
                    f'        for (uint32_t _i = 0; _i < (uint32_t)_count; _i++)',
                    f'            npt_decode_{field.type_name}(dec, ({field.type_name} *)&{acc}[_i]);',
                    f'    }} else if (_count) {{',
                    f'        npt_cs_decoder_set_fatal(dec); /* data sent but no buffer */',
                    f'    }}',
                    f'}}',
                ]

    def _decode_fixed_array(self, field, acc, prefix, inline_storage=True):
        """Decode a fixed-size array.

        When ``inline_storage=True`` (struct fields, e.g., ``val->Transform``),
        the storage is part of the parent struct so we just write into it.

        When ``inline_storage=False`` (command args, e.g., ``args->ColorRGBA``),
        ``c_type`` bumped the field's indirection to 1 in the generated args
        struct, so the field is a NULL pointer that needs temp storage allocated
        before we can decode into it.
        """
        count_expr = self._get_count_expr(field, prefix)
        base = self.reg.resolve_alias_chain(field.type_name)
        if base in PRIMITIVE_NAMES or field.is_enum:
            if inline_storage:
                return [
                    f'(void)npt_decode_array_count(dec, {count_expr});',
                    f'npt_decode_{field.type_name}_array(dec, ({field.type_name} *){acc}, {count_expr});',
                ]
            return [
                f'(void)npt_decode_array_count(dec, {count_expr});',
                f'{acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof({field.type_name}), ({count_expr}));',
                f'if (!{acc}) return;',
                f'npt_decode_{field.type_name}_array(dec, ({field.type_name} *){acc}, {count_expr});',
            ]
        else:
            if inline_storage:
                return [
                    f'(void)npt_decode_array_count(dec, {count_expr});',
                    f'for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                    f'    npt_decode_{field.type_name}(dec, ({field.type_name} *)&{acc}[_i]);',
                ]
            return [
                f'(void)npt_decode_array_count(dec, {count_expr});',
                f'{acc} = npt_cs_decoder_alloc_temp_array(dec, sizeof({field.type_name}), ({count_expr}));',
                f'if (!{acc}) return;',
                f'for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                f'    npt_decode_{field.type_name}(dec, ({field.type_name} *)&{acc}[_i]);',
            ]

    @staticmethod
    def _alloc_temp_guarded(acc, cond, alloc_call, memset_size, ind):
        """Emit an ``if (cond) { alloc; check; memset } else { acc = NULL }`` block."""
        return '\n'.join([
            f'{ind}if ({cond}) {{',
            f'{ind}    {acc} = {alloc_call};',
            f'{ind}    if (!{acc}) return;',
            f'{ind}    memset({acc}, 0, {memset_size});',
            f'{ind}}} else {{',
            f'{ind}    {acc} = NULL;',
            f'{ind}}}',
        ])

    def _decode_output_alloc(self, field, prefix, indent=1):
        """For output-only params on host decode: just allocate temp storage."""
        acc = self._acc(field, prefix)
        ind = '    ' * indent
        if field.indirection == 2 and field.is_com_handle:
            count_expr = self._get_count_expr(field, prefix)
            if count_expr:
                return self._alloc_temp_guarded(
                    acc, count_expr,
                    f'npt_cs_decoder_alloc_temp_array(dec, sizeof(void *), {count_expr})',
                    f'sizeof(void *) * {count_expr}', ind)
            return '\n'.join([
                f'{ind}{acc} = npt_cs_decoder_alloc_temp(dec, sizeof(void *));',
                f'{ind}if (!{acc}) return;',
                f'{ind}*{acc} = NULL;',
            ])
        if field.indirection == 1 and field.output:
            # Use the size field if available (for blob outputs like void* with size)
            size_expr = self._get_count_expr(field, prefix)
            if size_expr and field.type_name in ('void', 'VOID'):
                return self._alloc_temp_guarded(
                    acc, size_expr,
                    f'npt_cs_decoder_alloc_temp(dec, {size_expr})',
                    size_expr, ind)
            if size_expr:
                return self._alloc_temp_guarded(
                    acc, size_expr,
                    f'npt_cs_decoder_alloc_temp_array(dec, sizeof({field.type_name}), {size_expr})',
                    f'sizeof({field.type_name}) * {size_expr}', ind)
            return '\n'.join([
                f'{ind}{acc} = npt_cs_decoder_alloc_temp(dec, sizeof({field.type_name}));',
                f'{ind}if (!{acc}) return;',
                f'{ind}memset({acc}, 0, sizeof({field.type_name}));',
            ])
        return f'{ind}/* skip {prefix}{field.name} (output only, no alloc needed) */'

    # ------------------------------------------------------------------
    # Internal: condition wrapping
    # ------------------------------------------------------------------

    def _wrap_condition(self, field, lines, prefix, indent):
        """Wrap generated lines in a condition check if field has one."""
        if not lines:
            return ''

        ind = '    ' * indent
        code = '\n'.join(f'{ind}{line}' for line in lines)

        cond = field.condition
        if cond is None:
            return code
        if cond is False:
            return f'{ind}/* {field.name}: condition=false, always skip */'
        if isinstance(cond, str):
            # Replace self. with the struct accessor
            c_expr = cond.replace('self.', prefix)
            return f'{ind}if ({c_expr}) {{\n{code}\n{ind}}}'
        return code

    # ------------------------------------------------------------------
    # Handle replacement pass
    # ------------------------------------------------------------------

    def replace_handle_field(self, field: NptField, prefix: str,
                             indent: int = 1) -> str:
        """
        Generate handle replacement code for a field.
        Walks nested structs to replace COM/Win32 object IDs with real pointers.
        Called on host side after decode, before dispatch.
        """
        inner = self._anonymous_inner_fields(field)
        if inner is not None:
            return '\n'.join(p for p in
                             (self.replace_handle_field(f, prefix, indent)
                              for f in inner) if p)
        lines = self._replace_handle_field_impl(field, prefix)
        return self._wrap_condition(field, lines, prefix, indent)

    def _replace_handle_field_impl(self, field: NptField, prefix: str) -> list:
        """Return raw (un-indented) lines for the handle-replace pass on a
        single named field.  ``replace_handle_field`` wraps the result with
        ``_wrap_condition`` so per-arm overlay conditions gate execution the
        same way they do for sizeof/encode/decode."""
        acc = self._acc(field, prefix)

        # COM handle field — replace raw object ID with real pointer
        if field.is_com_handle:
            if field.indirection == 2 and field.output:
                return []  # output handles don't need replacement
            obj_type = self._object_type_for_field(field)
            if field.indirection == 2 and field.input and field.count is not None:
                # Input array of COM handles (e.g. ppRenderTargetViews):
                # iterate and replace each element.  The decoder filled the
                # array with raw object ids cast to void*.
                count_expr = self._get_count_expr(field, prefix)
                if count_expr:
                    return [
                        f'if ({acc}) {{',
                        f'    for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                        f'        {acc}[_i] = npt_cs_handle_lookup(ctx,',
                        f'            (npt_object_id)(uintptr_t){acc}[_i], {obj_type});',
                        f'}}',
                    ]
                return []
            if field.indirection >= 1:
                # Pointer field: decode stored npt_object_id in the pointer
                return [f'{acc} = npt_cs_handle_lookup(ctx, '
                        f'(npt_object_id)(uintptr_t){acc}, {obj_type});']
            # Value field: the uint64_t IS the object ID
            return [f'{acc} = (uintptr_t)npt_cs_handle_lookup(ctx, '
                    f'(npt_object_id){acc}, {obj_type});']

        # Win32 handle field
        if field.is_win32_handle:
            if field.output and not field.input:
                return []  # output-only handles don't need replacement
            if field.indirection >= 1:
                return [f'{acc} = npt_win32_handle_replace(ctx, '
                        f'(npt_object_id)(uintptr_t){acc});']
            return [f'{acc} = ({field.type_name})(uintptr_t)npt_win32_handle_replace(ctx, '
                    f'(npt_object_id){acc});']

        # Interface ref without explicit handle annotation
        if field.indirection >= 1 and self.reg.is_interface_type(field.type_name):
            obj_type = f'NPT_OBJECT_TYPE_{field.type_name.upper()}'
            return [f'{acc} = npt_cs_handle_lookup(ctx, '
                    f'(npt_object_id)(uintptr_t){acc}, {obj_type});']

        # Struct/union value that might contain handles — recurse
        if field.indirection == 0 and (field.is_struct or field.is_union):
            if self._type_might_contain_handle(field.type_ref):
                return [f'npt_replace_{field.type_name}_handle(ctx, &{acc});']
            return []

        # Pointer to struct that might contain handles
        if field.indirection == 1 and field.count is None and \
                (field.is_struct or field.is_union):
            if self._type_might_contain_handle(field.type_ref):
                return [
                    f'if ({acc})',
                    f'    npt_replace_{field.type_name}_handle(ctx, ({field.type_name} *){acc});',
                ]
            return []

        # Array of structs that might contain handles
        if field.indirection == 1 and field.count is not None and \
                (field.is_struct or field.is_union):
            if self._type_might_contain_handle(field.type_ref):
                count_expr = self._get_count_expr(field, prefix)
                if count_expr:
                    return [
                        f'if ({acc}) {{',
                        f'    for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                        f'        npt_replace_{field.type_name}_handle(ctx, &(({field.type_name} *){acc})[_i]);',
                        f'}}',
                    ]
            return []

        # Array of pointers to structs that might contain handles
        # (T**+count, e.g. D3D12_GENERIC_PROGRAM_DESC.ppSubobjects).
        # acc[_i] is already T*, so pass it directly to npt_replace_<T>_handle.
        if field.indirection >= 2 and field.count is not None and not field.is_handle \
                and (field.is_struct or field.is_union):
            if self._type_might_contain_handle(field.type_ref):
                count_expr = self._get_count_expr(field, prefix)
                if count_expr:
                    return [
                        f'if ({acc}) {{',
                        f'    for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                        f'        npt_replace_{field.type_name}_handle(ctx, ({field.type_name} *){acc}[_i]);',
                        f'}}',
                    ]
            return []

        # Fixed-size embedded array of structs with handles
        if field.indirection == 0 and field.is_fixed_array and \
                (field.is_struct or field.is_union):
            if self._type_might_contain_handle(field.type_ref):
                count_expr = self._get_count_expr(field, prefix)
                return [
                    f'for (uint32_t _i = 0; _i < (uint32_t)({count_expr}); _i++)',
                    f'    npt_replace_{field.type_name}_handle(ctx, &{acc}[_i]);',
                ]
            return []

        return []

    def register_output_handle_field(self, field: NptField, prefix: str,
                                     indent: int = 1,
                                     riid_expr: Optional[str] = None) -> str:
        """
        Generate handle registration code for an output COM handle field.
        Called on host side after the dispatched method returns so the
        produced COM pointers are entered in the context object table.

        When `riid_expr` is non-None and the field's type is void (the
        classic riid-based Create pattern, e.g. QueryInterface or
        D3D12CreateDevice), the emitted code resolves the type at
        runtime via `npt_object_type_from_iid`.  Otherwise void* outputs
        without a riid are skipped -- the consumer's override must
        register them.  Static-type outputs always emit direct
        registration with the compile-time type.
        """
        if not field.output:
            return ''
        if not field.is_com_handle:
            return ''

        inner = self._anonymous_inner_fields(field)
        if inner is not None:
            return '\n'.join(p for p in
                             (self.register_output_handle_field(
                                 f, prefix, indent, riid_expr)
                              for f in inner) if p)

        acc = self._acc(field, prefix)
        ind = '    ' * indent

        if field.type_name in ('void', 'VOID'):
            # riid + void** pattern: resolve the riid at runtime.  The
            # guest_id was decoded from the command body earlier; we
            # register {guest_id -> host_ptr} so subsequent method
            # dispatches against that id find the dxvk pointer.
            if riid_expr is None:
                return ''
            if field.indirection != 2:
                return ''
            return (
                f'{ind}if ({acc} && *{acc})\n'
                f'{ind}    npt_cs_handle_register_guest_id(ctx, '
                f'{prefix}_guest_id_{field.name}, *{acc},\n'
                f'{ind}        npt_object_type_from_iid({riid_expr}));'
            )

        obj_type = self._object_type_for_field(field)

        # Output double-pointer: either Create* returning a single object
        # (T **pp) or Create* returning an array (T ***pp + count).
        if field.indirection == 2:
            count_expr = self._get_count_expr(field, prefix)
            if count_expr:
                return (f'{ind}if ({acc} && {prefix}_guest_ids_{field.name}) {{\n'
                        f'{ind}    const uint32_t _n = '
                        f'{prefix}_guest_id_count_{field.name};\n'
                        f'{ind}    for (uint32_t _i = 0; _i < _n; _i++)\n'
                        f'{ind}        npt_cs_handle_register_guest_id(ctx,\n'
                        f'{ind}            {prefix}_guest_ids_{field.name}[_i], '
                        f'{acc}[_i], {obj_type});\n'
                        f'{ind}}}')
            return (f'{ind}if ({acc} && *{acc})\n'
                    f'{ind}    npt_cs_handle_register_guest_id(ctx, '
                    f'{prefix}_guest_id_{field.name}, *{acc}, {obj_type});')

        return ''

    def _riid_expr_for(self, params, prefix: str) -> Optional[str]:
        """Return a C expression that evaluates to a const GUID * if
        the parameter list has an IID input field, else None.  Used to
        drive runtime type resolution for riid-based Create /
        QueryInterface methods."""
        for p in params:
            if not p.input:
                continue
            if p.type_name != 'IID':
                continue
            if p.indirection == 1:
                # Already a pointer (REFIID / const IID *)
                return f'{prefix}{p.name}'
            if p.indirection == 0:
                # Inline IID value -- take its address.
                return f'&{prefix}{p.name}'
        return None

    def _type_might_contain_handle(self, ntype, _visited=None):
        """Check recursively if a struct/union type contains any handle fields."""
        if ntype is None:
            return False
        if _visited is None:
            _visited = set()
        if ntype.name in _visited:
            return False  # break cycles (self-referential pNext etc.)
        _visited.add(ntype.name)
        for field in ntype.fields:
            if field.is_handle:
                return True
            if self.reg.is_interface_type(field.type_name):
                return True
            ref = field.type_ref
            if ref and ref.category in (Category.STRUCT, Category.UNION):
                if self._type_might_contain_handle(ref, _visited):
                    return True
        return False

    def type_needs_replace_handle(self, ntype):
        """Public API: does this type need a npt_replace_*_handle function?"""
        return self._type_might_contain_handle(ntype)

    # ------------------------------------------------------------------
    # Helpers for dispatch / template code generation
    # ------------------------------------------------------------------

    @staticmethod
    def method_full_name(iface_name, method_name):
        """Canonical '{Interface}_{Method}' name used for command structs."""
        return f'{iface_name}_{method_name}'

    def param_decl(self, p):
        """Format a parameter as 'CType name' for C declarations."""
        return f'{self.c_type(p)} {p.name}'

    @staticmethod
    def thunk_name(iface_name, method_name):
        """Default thunk name for a COM method."""
        return f'npt_{iface_name.lower()}_default_{method_name}'

    def _object_type_for_field(self, field):
        """Get NPT_OBJECT_TYPE_XXX for a handle field.  Resolves through
        interface-to-interface type aliases (e.g. ID3DBlob -> ID3D10Blob)
        so the emitted macro always matches a real NPT_OBJECT_TYPE_*
        #define in npt_protocol_defs.h."""
        type_name = field.type_name
        if type_name == 'void':
            return 'NPT_OBJECT_TYPE_UNKNOWN'
        base = self.reg.resolve_alias_chain(type_name)
        return f'NPT_OBJECT_TYPE_{base.upper()}'

    def parent_interface_name(self, iface):
        """Return the name of the parent interface, or None if the
        parent is IUnknown or the root.  Used by the parent table
        template to emit the base class for runtime upcast checks.
        IUnknown itself is registered so its parent is 0."""
        parent = getattr(iface, 'parent', None)
        parent_name = getattr(iface, 'parent_name', None)
        name = parent.name if parent else parent_name
        if not name or name == 'IUnknown':
            return None
        return name

    def pfn_typedef_name(self, iface_name: str, method_name: str):
        """Global typedef name for a COM vtable function pointer."""
        return f'PFN_{iface_name}_{method_name}'

    def vtable_call_args(self, method: NptMethod, iface_name: str):
        """
        Generate the typedef and call for a default COM vtable call.
        Returns (pfn_name, typedef_str, call_args_str, vtable_index).
        """
        ret_type = self.ret_type_str(method.return_type)
        param_types = ['void *']  # 'this' pointer
        param_names = ['args._self']

        for p in method.params:
            c_decl = self.c_type(p)
            param_types.append(c_decl)
            param_names.append(f'args.{p.name}')

        typedef_params = ', '.join(param_types)
        pfn_name = self.pfn_typedef_name(iface_name, method.name)
        typedef = f'typedef {ret_type} (NPT_STDMETHODCALLTYPE *{pfn_name})({typedef_params})'
        call_args = ', '.join(param_names)

        return pfn_name, typedef, call_args, method.vtable_index

    @staticmethod
    def function_pfn_typedef_name(func_name: str):
        """Global typedef name for a top-level function pointer."""
        return f'PFN_{func_name}'

    def function_pfn_typedef(self, func):
        """
        Generate the typedef line for a top-level function pointer
        (e.g. PFN_D3D11CreateDevice).  Mirrors `vtable_call_args` but
        without the leading 'this' parameter.
        """
        ret_type = self.ret_type_str(func.return_type)
        param_types = [self.c_type(p) for p in func.params] or ['void']
        pfn_name = self.function_pfn_typedef_name(func.name)
        return f'typedef {ret_type} (*{pfn_name})({", ".join(param_types)})'
