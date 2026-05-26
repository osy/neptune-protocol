# Copyright 2026 Turing Software LLC
# SPDX-License-Identifier: Apache-2.0

tests_inc = include_directories('.')

if cc.get_id() == 'msvc' or cc.get_id() == 'clang-cl'
  test_c_args = [
    '/wd4100',  # unreferenced formal parameter (=-Wno-unused-parameter)
    '/wd4505',  # unreferenced local function has been removed (=-Wno-unused-function)
    '/wd4189',  # local variable is initialized but not referenced
    '/wd4101',  # unreferenced local variable
    '/wd4127',  # conditional expression is constant
    '/wd4244',  # conversion, possible loss of data
    '/wd4267',  # conversion from size_t, possible loss of data
    '/wd4245',  # conversion from int to unsigned, signed/unsigned mismatch
    '/wd4389',  # signed/unsigned mismatch
    '/wd4018',  # signed/unsigned mismatch in comparison
    '/wd4459',  # declaration of X hides global declaration
    '/wd4456',  # declaration of X hides previous local declaration
    '/wd4457',  # declaration of X hides function parameter
  ]
else
  test_c_args = [
    '-Wno-unused-function',
    '-Wno-unused-parameter',
  ]
endif

# --- Test generator ---
npt_testgen_outputs = [
  'test_roundtrip_guest.c',
  'test_roundtrip_host.c',
  'test_roundtrip.c',
  'npt_test_ids.h',
]

npt_testgen = custom_target(
  'npt_testgen',
  input: ['../tools/npt_testgen.py'],
  output: npt_testgen_outputs,
  command: [
    py, '@INPUT0@',
    '--outdir', meson.current_build_dir(),
    '--json', meson.current_source_dir() / '..' / npt_json,
    '--overlay', meson.current_source_dir() / '..' / npt_overlay,
  ],
  depend_files: [
    npt_json_files,
  ],
  build_by_default: true,
)

# --- Roundtrip test ---
# Two static libraries because host and guest protocol headers conflict
# (same-named static inline functions).

test_roundtrip_host_lib = static_library(
  'test_roundtrip_host',
  npt_testgen[1],  # test_roundtrip_host.c
  'test_roundtrip_manual.c',
  npt_testgen[3],  # npt_test_ids.h (header dep)
  npt_protocol_host,
  npt_protocol_directx_types,
  include_directories: [tests_inc],
  c_args: test_c_args,
)

test_roundtrip_guest_lib = static_library(
  'test_roundtrip_guest',
  npt_testgen[0],  # test_roundtrip_guest.c
  'test_roundtrip_manual_guest.c',
  npt_testgen[3],  # npt_test_ids.h (header dep)
  npt_protocol_guest,
  npt_protocol_host,  # for npt_protocol_defs.h
  npt_protocol_directx_types,
  include_directories: [tests_inc],
  c_args: test_c_args,
)

test_roundtrip = executable(
  'test_roundtrip',
  npt_testgen[2],  # test_roundtrip.c (main runner only)
  npt_testgen[3],  # npt_test_ids.h (header dep)
  link_with: [test_roundtrip_host_lib, test_roundtrip_guest_lib],
  include_directories: [tests_inc],
  c_args: test_c_args,
)

test('roundtrip', test_roundtrip, timeout: 120)
