#!/usr/bin/env python3
"""Convert MIDL IDL files to npt_registry.json using midl_classic.

Usage:
    python convert_midl.py file1.idl file2.idl ... [-o output.json]

The IDL files should be listed in dependency order (base types first).
"""

import argparse
import json
import os
import re
import sys

from midl_classic import *

# ---------------------------------------------------------------------------
# Implicit pointer/const typedefs: (base_type, is_const)
# These are decomposed into their base type with proper indirection/const.
# ---------------------------------------------------------------------------

IMPLICIT_POINTER_TYPES = {
    "REFGUID":  ("GUID",  True),
    "REFIID":   ("IID",   True),
    "REFCLSID": ("CLSID", True),
    "LPCSTR":   ("CHAR",  True),
    "LPSTR":    ("CHAR",  False),
    "LPCWSTR":  ("WCHAR", True),
    "LPWSTR":   ("WCHAR", False),
    "LPCVOID":  ("VOID",  True),
    "LPVOID":   ("VOID",  False),
}

# Types that map to win32 handles
HANDLE_TYPES = {"HANDLE", "HWND", "HMODULE"}

# Base COM interfaces not defined in the input IDLs
BASE_INTERFACES = {"IUnknown", "ID3DBlob", "ID3D10Blob"}

# ---------------------------------------------------------------------------
# Expression evaluator
# ---------------------------------------------------------------------------

class ExpressionEvaluator:
    """Evaluates constant expressions to integer values."""

    def __init__(self):
        self.known_values: dict[str, int] = {}

    def register(self, name: str, value: int):
        self.known_values[name] = value

    def evaluate(self, expr) -> int | None:
        if isinstance(expr, IntegerLiteral):
            return expr.value
        if isinstance(expr, FloatLiteral):
            return None
        if isinstance(expr, StringLiteral):
            return None
        if isinstance(expr, IdentifierRef):
            return self.known_values.get(expr.name)
        if isinstance(expr, ParenExpr):
            return self.evaluate(expr.inner)
        if isinstance(expr, UnaryOp):
            val = self.evaluate(expr.operand)
            if val is None:
                return None
            if expr.op == "-":
                return -val
            if expr.op == "~":
                return ~val
            if expr.op == "!":
                return int(not val)
            return None
        if isinstance(expr, BinaryOp):
            left = self.evaluate(expr.left)
            right = self.evaluate(expr.right)
            if left is None or right is None:
                return None
            op = expr.op
            if op == "|":
                return left | right
            if op == "&":
                return left & right
            if op == "^":
                return left ^ right
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                return left // right if right != 0 else None
            if op == "%":
                return left % right if right != 0 else None
            if op == "<<":
                return left << right
            if op == ">>":
                return left >> right
            return None
        return None


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

class MidlConverter:
    """Converts parsed MIDL AST nodes to npt_types.json format."""

    def __init__(self):
        self.evaluator = ExpressionEvaluator()
        self.known_interfaces: set[str] = set(BASE_INTERFACES)
        self.types: list[dict] = []
        self.source_files: list[str] = []

    # -- Type resolution ---------------------------------------------------

    def resolve_type(self, ts: TypeSpec) -> tuple[str, int, bool, str | None]:
        """Resolve a TypeSpec to (type_name, indirection, is_const, handle_kind).

        handle_kind is "com" for interface types, "win32" for native handle
        types (HANDLE, HWND, HMODULE), or None for non-handle types.
        """
        base = ts.base_name
        indirection = ts.pointer_depth
        is_const = ts.is_const
        handle_kind = None

        # Decompose implicit pointer typedefs into base type + indirection
        if base in IMPLICIT_POINTER_TYPES:
            base, impl_const = IMPLICIT_POINTER_TYPES[base]
            indirection += 1
            is_const = is_const or impl_const

        # Check if this is an interface type -> com handle
        if base in self.known_interfaces:
            handle_kind = "com"

        # Check native handle types -> win32 handle
        if base in HANDLE_TYPES:
            handle_kind = "win32"

        return base, indirection, is_const, handle_kind

    @staticmethod
    def _strip_deref(expr: str) -> str:
        """Strip leading pointer dereference(s) from a size expression."""
        return expr.lstrip("*").strip()

    # -- Annotation handling -----------------------------------------------

    def apply_annotation(self, field: dict, ann: ParsedAnnotation):
        """Apply a parsed SAL annotation to a field dict."""
        if ann.kind == AnnotationKind.COM_OUTPTR:
            field["handle"] = "com"
            field["output"] = True
            field["input"] = False
            if ann.optional:
                field["optional"] = True
            return

        if ann.kind == AnnotationKind.OUTPTR:
            field["output"] = True
            field["input"] = False
            if ann.optional:
                field["optional"] = True
            if ann.size_expr:
                field["count"] = self._strip_deref(ann.size_expr)
            return

        if ann.kind == AnnotationKind.FIELD_SIZE:
            if ann.size_expr:
                field["count"] = self._strip_deref(ann.size_expr)
            if ann.optional:
                field["optional"] = True
            # Byte-sized field annotations need the type overridden to void
            if ann.access == AnnotationAccess.FIELD_SIZE_BYTES:
                _BYTE_TYPES = {"BYTE", "UCHAR", "CHAR", "UINT8", "INT8",
                               "void", "VOID"}
                ftype = field.get("type", "")
                if ftype not in _BYTE_TYPES:
                    print(
                        f"WARNING: FIELD_SIZE_BYTES annotation on "
                        f"'{field.get('name')}': overriding type "
                        f"'{ftype}' to 'void'",
                        file=sys.stderr,
                    )
                    field["type"] = "void"
            return

        if ann.kind == AnnotationKind.NUL_TERMINATED:
            # Direction is IN, which is the default
            return

        if ann.kind == AnnotationKind.RANGE:
            # Range info is informational; no schema field for it
            return

        # PARAM kind (or OTHER fallthrough)
        if ann.direction == AnnotationDirection.IN:
            pass  # input=True is the default
        elif ann.direction == AnnotationDirection.OUT:
            field["output"] = True
            field["input"] = False
        elif ann.direction == AnnotationDirection.INOUT:
            field["output"] = True
            # input=True is the default

        if ann.optional:
            field["optional"] = True

        if ann.access != AnnotationAccess.NONE:
            # Byte-sized annotations require a byte/void type
            _BYTE_ACCESS = (
                AnnotationAccess.READS_BYTES,
                AnnotationAccess.WRITES_BYTES,
                AnnotationAccess.WRITES_BYTES_TO,
                AnnotationAccess.UPDATES_BYTES,
                AnnotationAccess.FIELD_SIZE_BYTES,
            )
            if ann.access in _BYTE_ACCESS:
                _BYTE_TYPES = {"BYTE", "UCHAR", "CHAR", "UINT8", "INT8", "void", "VOID"}
                ftype = field.get("type", "")
                if ftype not in _BYTE_TYPES:
                    print(
                        f"WARNING: {ann.access.value} annotation on "
                        f"'{field.get('name')}': overriding type '{ftype}' "
                        f"to 'void'",
                        file=sys.stderr,
                    )
                    field["type"] = "void"

            if ann.access in (AnnotationAccess.WRITES_TO, AnnotationAccess.WRITES_BYTES_TO):
                if ann.capacity_expr:
                    field["count"] = self._strip_deref(ann.capacity_expr)
                if ann.size_expr:
                    field["count_output"] = self._strip_deref(ann.size_expr)
            elif ann.size_expr:
                field["count"] = self._strip_deref(ann.size_expr)


    # -- Array dimension handling ------------------------------------------

    def _eval_array_dim(self, dim: ArrayDimension) -> int | str | None:
        """Evaluate an array dimension to an integer or string."""
        if dim.size is None:
            return None
        if isinstance(dim.size, IntegerLiteral):
            return dim.size.value
        if isinstance(dim.size, IdentifierRef):
            val = self.evaluator.known_values.get(dim.size.name)
            if val is not None:
                return val
            return dim.size.name
        # Try numeric evaluation
        val = self.evaluator.evaluate(dim.size)
        if val is not None:
            return val
        return None

    # -- Field conversion --------------------------------------------------

    def convert_struct_field(self, f: StructField) -> dict:
        """Convert a StructField to a FieldObject dict."""
        type_name, indirection, is_const, handle_kind = self.resolve_type(f.type_spec)

        field: dict = {"name": f.name, "type": type_name}
        if indirection:
            field["indirection"] = indirection
        if is_const:
            field["const"] = True
        if handle_kind:
            field["handle"] = handle_kind

        # Array dimensions -> size
        if f.array_dimensions:
            dims = [self._eval_array_dim(d) for d in f.array_dimensions]
            dims = [d for d in dims if d is not None]
            if len(dims) == 1:
                field["count"] = dims[0]
            elif len(dims) > 1:
                # Multi-dimensional: all must be integers
                if all(isinstance(d, int) for d in dims):
                    field["count"] = dims
                else:
                    raise ValueError(
                        f"multi-dimensional array with non-integer dims "
                        f"in {field.get('name', '?')}: {dims}")

        # Bitfield
        if f.bitfield_width is not None:
            field["bitwidth"] = f.bitfield_width

        # SAL annotation
        ann = f.parsed_annotation
        if ann:
            self.apply_annotation(field, ann)

        return field

    def convert_struct_member(self, m) -> dict:
        """Convert a StructMember (StructField, AnonymousUnion, AnonymousStruct)."""
        if isinstance(m, StructField):
            return self.convert_struct_field(m)

        if isinstance(m, AnonymousUnion):
            fields = [self.convert_struct_member(sub) for sub in m.members]
            inline_type = {"primitive": "union", "fields": fields}
            return {"name": m.name, "type": inline_type}

        if isinstance(m, AnonymousStruct):
            fields = [self.convert_struct_member(sub) for sub in m.members]
            inline_type = {"primitive": "struct", "fields": fields}
            return {"name": m.name, "type": inline_type}

        return {"name": str(m)}

    # -- Top-level element converters --------------------------------------

    def convert_constant(self, c: Constant, source: str) -> dict | None:
        val = self.evaluator.evaluate(c.value)
        if val is None:
            return None
        self.evaluator.register(c.name, val)
        return {"name": c.name, "primitive": "const", "value": val, "source": source}

    def convert_enum(self, e: EnumDef, source: str) -> dict:
        fields = []
        next_val = 0
        for member in e.members:
            if member.value is not None:
                val = self.evaluator.evaluate(member.value)
                if val is not None:
                    next_val = val
                else:
                    raise ValueError(
                        f"could not evaluate enum value for "
                        f"{e.name}.{member.name}")
            entry: dict = {"name": member.name, "value": next_val}
            self.evaluator.register(member.name, next_val)
            fields.append(entry)
            next_val += 1
        return {"name": e.name, "primitive": "enum", "fields": fields, "source": source}

    def convert_struct(self, s: StructDef, source: str) -> dict:
        fields = [self.convert_struct_member(m) for m in s.members]
        return {"name": s.name, "primitive": "struct", "fields": fields, "source": source}

    def convert_union(self, u: UnionDef, source: str) -> dict:
        fields = []
        if u.members:
            fields = [self.convert_struct_member(m) for m in u.members]
        if u.cases:
            for case in u.cases:
                if case.member is None:
                    continue
                if isinstance(case.member, StructField):
                    fields.append(self.convert_struct_field(case.member))
                elif isinstance(case.member, AnonymousStruct):
                    sub_fields = [self.convert_struct_field(f) for f in case.member.members]
                    inline_type = {"primitive": "struct", "fields": sub_fields}
                    fields.append({"name": case.member.name, "type": inline_type})
        return {"name": u.name, "primitive": "union", "fields": fields, "source": source}

    def convert_typedef(self, t: TypeAlias, source: str) -> dict | None:
        type_name, indirection, is_const, _ = self.resolve_type(t.type_spec)
        if indirection > 0:
            # Pointer typedefs (like typedef void* HANDLE) are not directly
            # representable as top-level TypeObject. Skip them.
            return None
        if t.name == type_name:
            return None  # Identity typedef
        return {"name": t.name, "primitive": type_name, "source": source}

    def convert_method_param(self, p, idx: int) -> dict:
        """Convert a MethodParam to a FieldObject dict."""
        type_name, indirection, is_const, handle_kind = self.resolve_type(p.type_spec)

        field: dict = {"name": p.name, "type": type_name}
        if indirection:
            field["indirection"] = indirection
        if is_const:
            field["const"] = True
        if handle_kind:
            field["handle"] = handle_kind

        # Array dimensions
        if p.array_dimensions:
            dims = [self._eval_array_dim(d) for d in p.array_dimensions]
            dims = [d for d in dims if d is not None]
            if len(dims) == 1:
                field["count"] = dims[0]
            elif len(dims) > 1:
                if all(isinstance(d, int) for d in dims):
                    field["count"] = dims
                else:
                    raise ValueError(
                        f"multi-dimensional array with non-integer dims "
                        f"in param {field.get('name', '?')}: {dims}")

        # MIDL [size_is()] attribute
        if hasattr(p, "size_is") and p.size_is:
            field["count"] = self._strip_deref(p.size_is)

        # SAL annotation
        ann = p.parsed_annotation if hasattr(p, "parsed_annotation") else None
        if ann:
            self.apply_annotation(field, ann)

        # MIDL [in]/[out] attributes as fallback
        if hasattr(p, "is_in") and hasattr(p, "is_out"):
            if "input" not in field and "output" not in field:
                if p.is_out and not p.is_in:
                    field["output"] = True
                    field["input"] = False
                elif p.is_out and p.is_in:
                    field["output"] = True

        field["idl_param_index"] = idx
        return field

    def convert_method(self, m) -> dict:
        ret_type, _, _, _ = self.resolve_type(m.return_type)
        result: dict = {"name": m.name}
        if ret_type != "void":
            result["return"] = ret_type
        if m.params:
            result["params"] = [
                self.convert_method_param(p, i) for i, p in enumerate(m.params)
            ]
        return result

    def convert_interface(self, iface: InterfaceDef, source: str) -> list[dict]:
        """Convert an interface and any inline typedefs. Returns list of types."""
        self.known_interfaces.add(iface.name)
        result_types = []

        # Process inline typedefs as separate top-level types
        for itd in iface.typedefs:
            td = itd.typedef
            if isinstance(td, EnumDef):
                result_types.append(self.convert_enum(td, source))
            elif isinstance(td, StructDef):
                result_types.append(self.convert_struct(td, source))
            elif isinstance(td, UnionDef):
                result_types.append(self.convert_union(td, source))
            elif isinstance(td, TypeAlias):
                converted = self.convert_typedef(td, source)
                if converted:
                    result_types.append(converted)

        # Build interface object
        iface_obj: dict = {
            "name": iface.name,
            "primitive": "interface",
            "source": source,
        }
        if iface.uuid:
            iface_obj["uuid"] = iface.uuid
        if iface.parent:
            iface_obj["parent"] = iface.parent
        if iface.methods:
            iface_obj["methods"] = [self.convert_method(m) for m in iface.methods]

        result_types.append(iface_obj)
        return result_types

    # -- cpp_quote function parsing ----------------------------------------

    def parse_cpp_quote_functions(self, elements: list, source: str) -> list[dict]:
        """Extract function declarations from consecutive cpp_quote blocks."""
        functions = []

        # Accumulate consecutive CppQuote texts
        blocks: list[str] = []
        current: list[str] = []

        for elem in elements:
            if isinstance(elem, CppQuote):
                current.append(elem.text)
            else:
                if current:
                    blocks.append("\n".join(current))
                    current = []
        if current:
            blocks.append("\n".join(current))

        for block in blocks:
            functions.extend(self._parse_function_block(block, source))

        return functions

    def _parse_function_block(self, text: str, source: str) -> list[dict]:
        """Parse function declarations from a cpp_quote text block."""
        results = []

        # Match non-typedef function declarations: RETURN_TYPE WINAPI NAME(...)
        # Allow multi-line with re.DOTALL
        pattern = re.compile(
            r'(?<!\w)(?!typedef\b)(\w+)\s+WINAPI\s+(\w+)\s*\('
            r'((?:[^()]*|\((?:[^()]*|\([^()]*\))*\))*)\)\s*;',
            re.DOTALL,
        )

        for m in pattern.finditer(text):
            ret_type_str = m.group(1)
            func_name = m.group(2)
            params_str = m.group(3).strip()

            ret_type = ret_type_str

            func: dict = {
                "name": func_name,
                "primitive": "function",
                "source": source,
            }
            if ret_type != "void":
                func["return"] = ret_type

            if params_str and params_str.lower() != "void":
                params = self._parse_function_params(params_str)
                if params:
                    func["params"] = params

            results.append(func)

        return results

    def _parse_function_params(self, params_str: str) -> list[dict]:
        """Parse a comma-separated parameter list from a C function prototype."""
        params = []

        # Split on commas, but not within parentheses
        parts = self._split_params(params_str)

        for idx, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            param = self._parse_single_param(part, idx)
            if param:
                params.append(param)

        return params

    def _split_params(self, s: str) -> list[str]:
        """Split parameter string on commas, respecting parentheses."""
        parts = []
        depth = 0
        current = []
        for ch in s:
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _parse_single_param(self, text: str, idx: int) -> dict | None:
        """Parse a single parameter from a C function prototype in cpp_quote."""
        # Strip inline // comments
        text = re.sub(r'//.*', '', text)
        text = text.strip()
        if not text:
            return None

        # Remove line continuations and normalize whitespace
        text = re.sub(r'\s+', ' ', text)

        annotation = None
        rest = text

        # Extract SAL annotation (starts with _)
        ann_match = re.match(r'(_\w+(?:\s*\([^)]*\))?)\s+(.*)', text)
        if ann_match:
            annotation = ann_match.group(1)
            rest = ann_match.group(2)

        # Parse: [CONST] TYPE [*...] NAME [[ N ]]
        is_const = False
        if rest.startswith("CONST ") or rest.startswith("const "):
            is_const = True
            rest = rest[6:]

        # Extract array suffix like [ 4 ]
        array_size = None
        arr_match = re.search(r'\[\s*(\w+)\s*\]\s*$', rest)
        if arr_match:
            arr_str = arr_match.group(1)
            try:
                array_size = int(arr_str)
            except ValueError:
                array_size = arr_str  # string reference
            rest = rest[:arr_match.start()].strip()

        # Split into tokens
        tokens = rest.split()
        if not tokens:
            return None

        # Separate pointer stars from type and name
        # Last token might be the name (or type if no name)
        pointers = 0
        param_name = None

        # Count leading/trailing stars; strip CONST between pointers
        cleaned = []
        for tok in tokens:
            while tok.startswith("*"):
                pointers += 1
                tok = tok[1:]
            while tok.endswith("*"):
                pointers += 1
                tok = tok[:-1]
            if tok and tok in ("CONST", "const"):
                is_const = True
                continue
            if tok:
                cleaned.append(tok)

        if len(cleaned) >= 2:
            type_name_raw = " ".join(cleaned[:-1])
            param_name = cleaned[-1]
        elif len(cleaned) == 1:
            type_name_raw = cleaned[0]
            param_name = None
        else:
            return None

        # Resolve type
        handle_kind = None
        type_name = type_name_raw

        # Decompose implicit pointer typedefs
        if type_name_raw in IMPLICIT_POINTER_TYPES:
            type_name, impl_const = IMPLICIT_POINTER_TYPES[type_name_raw]
            pointers += 1
            is_const = is_const or impl_const

        if type_name in self.known_interfaces:
            handle_kind = "com"
        elif type_name in HANDLE_TYPES:
            handle_kind = "win32"

        field: dict = {}
        if param_name:
            field["name"] = param_name
        field["type"] = type_name
        if pointers:
            field["indirection"] = pointers
        if is_const:
            field["const"] = True
        if handle_kind:
            field["handle"] = handle_kind
        if array_size is not None:
            field["count"] = array_size

        # Apply SAL annotation
        if annotation:
            ann = parse_sal_annotation(annotation)
            self.apply_annotation(field, ann)

        field["idl_param_index"] = idx
        return field

    # -- File processing ---------------------------------------------------

    def process_file(self, filepath: str):
        """Parse and convert a single IDL file."""
        midl = parse_file(filepath)
        source = os.path.basename(filepath)
        self.source_files.append(source)

        for elem in midl.elements:
            if isinstance(elem, Constant):
                result = self.convert_constant(elem, source)
                if result:
                    self.types.append(result)

            elif isinstance(elem, EnumDef):
                self.types.append(self.convert_enum(elem, source))

            elif isinstance(elem, StructDef):
                self.types.append(self.convert_struct(elem, source))

            elif isinstance(elem, UnionDef):
                self.types.append(self.convert_union(elem, source))

            elif isinstance(elem, TypeAlias):
                result = self.convert_typedef(elem, source)
                if result:
                    self.types.append(result)

            elif isinstance(elem, InterfaceDef):
                self.types.extend(self.convert_interface(elem, source))

            elif isinstance(elem, ForwardDecl):
                if elem.kind == "interface":
                    self.known_interfaces.add(elem.name)

            elif isinstance(elem, FuncPointerTypedef):
                pass  # Skip

        # Process cpp_quote function declarations
        functions = self.parse_cpp_quote_functions(midl.elements, source)
        self.types.extend(functions)

    def to_json(self) -> dict:
        """Build the final JSON output."""
        # Clean all output dicts
        cleaned_types = [clean_dict(t) for t in self.types]
        return {
            "version": 1,
            "source_files": self.source_files,
            "types": cleaned_types,
        }


# ---------------------------------------------------------------------------
# Output hygiene
# ---------------------------------------------------------------------------

def clean_dict(d: dict) -> dict:
    """Remove keys with schema-default values for cleaner output."""
    result = {}
    for key, val in d.items():
        # Remove None values (null is the default for "name" and "handle")
        if val is None:
            continue
        # Remove default values
        if key == "indirection" and val == 0:
            continue
        if key == "const" and val is False:
            continue
        if key == "input" and val is True:
            continue
        if key == "output" and val is False:
            continue
        if key == "optional" and val is False:
            continue
        # Recursively clean nested dicts and lists
        if isinstance(val, dict):
            val = clean_dict(val)
        elif isinstance(val, list):
            val = [clean_dict(item) if isinstance(item, dict) else item for item in val]
        result[key] = val
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert MIDL IDL files to npt_types.json",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="IDL files to parse (in dependency order)",
    )
    parser.add_argument(
        "-o", "--output",
        default="npt_protocol.json",
        help="Output JSON file (default: npt_protocol.json)",
    )
    args = parser.parse_args()

    converter = MidlConverter()

    for filepath in args.files:
        print(f"Processing {filepath}...", file=sys.stderr)
        converter.process_file(filepath)

    output = converter.to_json()

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    print(
        f"Wrote {len(output['types'])} types to {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
