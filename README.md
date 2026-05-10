# neptune-protocol

A code-generation toolchain that turns Microsoft DirectX MIDL definitions
into a wire protocol for serializing DXGI / Direct3D 11 / Direct3D 12 COM
calls between two processes (typically a guest and a host, e.g. a VM
graphics stack).

The repository ships:

- a JSON registry derived from the DirectX MIDL files (`npt_registry.json`),
- a small set of Python generators that turn the registry into C headers
  for both ends of the wire (`tools/`),
- Mako templates that drive the generators (`templates/`),
- a Meson build that wires everything together and runs a roundtrip test
  suite (`meson.build`, `tests/`).

The protocol itself — command/reply framing, encoding rules, COM-handle
representation, etc. — is documented in
[`docs/neptune_command_serialization.txt`](docs/neptune_command_serialization.txt).

## Repository layout

| Path | Purpose |
| --- | --- |
| `npt_registry.json` | Generated registry: every type, struct, enum, interface, and method extracted from the DirectX MIDL files. |
| `npt_registry_overlay.json` | Hand-written augmentations applied on top of the registry: typedef base types, top-level function group/id assignments, parameter directionality fixes, `skip_default` opt-outs, etc. |
| `npt_registry_schema.json` | JSON Schema (draft-07) describing the registry + overlay format. |
| `npt_interface_ids.json` | Authoritative GUID ↔ 16-bit interface-id pinning file. Once allocated, an id is **never** reused (protobuf field-number policy). |
| `tools/` | Python generators (see below). |
| `templates/` | Mako templates that the generators expand into C headers / sources. |
| `tests/` | Meson-driven roundtrip tests that encode and decode every method on every interface. |
| `docs/` | Protocol design notes. |
| `meson.build`, `meson_options.txt` | Build configuration. |

## Generators

All scripts live in `tools/` and are normally driven by Meson; they can
also be invoked directly.

| Script | Role |
| --- | --- |
| `convert_midl.py` | Parses MIDL `.idl` files (via the [`midl_classic`](https://pypi.org/project/midl-classic/) package) and emits `npt_registry.json`. Run only when refreshing against a new DirectX SDK. |
| `npt_protocol.py` | Main code generator. Emits host-side (decoder + dispatch), guest-side (encoder), and client-side (per-family COM client + IID→ctor table) C headers and sources from the registry + overlay. |
| `gen_headers.py` | Emits `npt_protocol_directx_types.h`, a Microsoft-layout-compatible C header containing all enums, structs, unions, typedefs, and forward declarations referenced by the protocol. |
| `npt_testgen.py` | Emits the roundtrip test sources consumed by `tests/`. |
| `npt_allocate_interface_id.py` | Allocates the next free 16-bit interface id in `npt_interface_ids.json` for a new `(name, guid)` pair. |
| `list_families.py` | Prints the sorted list of interface families. Used by `meson.build` to derive the per-family output file list at configure time. |

## Building

Prerequisites:

- Python 3 with [`mako`](https://www.makotemplates.org/) installed (only
  needed if Meson cannot find it via your distro packages).
- Meson ≥ 0.56.0 and Ninja.
- A C11 compiler.

```sh
meson setup builddir
ninja -C builddir
meson test -C builddir
```

The default Meson configuration generates code from `npt_registry.json`
and `npt_registry_overlay.json` in the source tree. Both paths can be
overridden:

```sh
meson setup builddir \
    -Djson=path/to/registry.json \
    -Doverlay=path/to/overlay.json
```

The build emits four custom-target groups into the build directory:

- `npt_protocol_directx_types` — Microsoft-layout C types header.
- `npt_protocol_host` — host (decoder + dispatch) headers, including
  shared `npt_protocol_defs.h`, `npt_protocol_common_*`, per-family
  headers, top-level function dispatch, and the umbrella
  `npt_protocol_host.h`.
- `npt_protocol_guest` — guest (encoder) headers, plus the umbrella
  `npt_protocol_guest.h`.
- `npt_protocol_client` — per-family COM client header + out-of-line
  `.c` bodies, the global IID→ctor table, and `npt_client_families.txt`.
  Compiled by the consumer (e.g. mesa), not by this repository.

## Refreshing the registry from MIDL

`npt_registry.json` is checked in but to regenerate it from Windows SDKs:

```sh
pip install midl-classic
./tools/convert_midl.py -o npt_registry.json \
    dxgiformat.idl \
    dxgicommon.idl \
    dxgitype.idl \
    dxgi.idl \
    dxgi1_2.idl \
    dxgi1_3.idl \
    dxgi1_4.idl \
    dxgi1_5.idl \
    dxgi1_6.idl \
    d3dcommon.idl \
    d3d11.idl \
    d3d11_1.idl \
    d3d11_2.idl \
    d3d11_3.idl \
    d3d11_4.idl \
    d3d11on12.idl \
    d3d12.idl
```

All MIDL files must live in the same directory; pass them in dependency
order (base types first). The conversion is idempotent — running it
against the same inputs produces the same output.

## Overlays

Overlays are JSON documents that share the registry schema and are merged
on top of `npt_registry.json` at every generator invocation. They carry
information that cannot be expressed in MIDL and is too small to justify
a fork of the SDK headers, for example:

- typedef base types (`{"name": "DWORD", "primitive": "uint32_t"}`),
- group/id assignments for top-level entry points like
  `D3D11CreateDevice` (top-level functions without a group/id are
  dropped from the wire),
- per-method tweaks such as `skip_default: true` to opt a method out of
  the generator's default thunk in favour of a hand-written one,
- per-parameter fixes (handle classification, input/output direction,
  array counts).

Multiple overlays can be passed; they are applied in order, and arrays of
typed objects are merged by `name` (or by `index` for positional
overrides). See `docs/neptune_command_serialization.txt` for the full
merge rules.

## Adding a new interface

When the generator encounters an interface whose GUID is not pinned in
`npt_interface_ids.json`, it refuses to emit code. To allocate the next
free id:

```sh
./tools/npt_allocate_interface_id.py ID3D11Foo aec22fb8-76f3-4639-9be0-28eb43a67a2e
```

The script is idempotent: repeated invocations with the same arguments
print the existing id rather than re-allocating. Retired interfaces stay
in the file with `"retired": true` so their slots are reserved forever.

## Tests

`tests/` builds a roundtrip executable that exercises every encode/decode
pair via generator-emitted fixtures. Run it through Meson:

```sh
meson test -C builddir
```

The `roundtrip` test has a 120-second timeout and exits non-zero on the
first mismatch.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
