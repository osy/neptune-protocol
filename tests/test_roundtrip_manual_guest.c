/*
 * Copyright 2026 Turing Software LLC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Guest-side manual roundtrip tests.  Lives in its own translation unit
 * because the guest and host protocol headers define same-named static
 * inline functions (cs_helpers, encode/decode) and cannot coexist in
 * one TU.  Linked into test_roundtrip_guest_lib; the host-side
 * test_roundtrip_manual.c calls these via extern.
 */

#include "npt_cs.h"
#include "npt_protocol_guest.h"
#include "npt_test_harness.h"

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

/* ================================================================== */
/* Optional FIXED_ARRAY input NULL-encoding tests                     */
/* ================================================================== */
/*
 * Pin the encoder contract for IDL-optional FIXED_ARRAY inputs: encoding
 * with the caller pointer set to NULL must not crash, and the wire must
 * carry array_count=0.  Auto-generated tests can't reach this — their
 * param initializers always allocate a non-NULL buffer for fixed counts.
 */

static int test_guest_OMSetBlendState_null_BlendFactor(void)
{
    uint8_t buf[128] = {0};
    struct npt_cs_encoder enc = npt_test_encoder_init(buf, sizeof(buf));
    ID3D11BlendState *fake_state = (ID3D11BlendState *)(uintptr_t)0x1000ULL;
    npt_encode_ID3D11DeviceContext_OMSetBlendState(&enc, 0, 0xDEAD,
                                                    fake_state, NULL, 0xff);
    size_t cmd_size = npt_test_encoder_written(&enc, buf);

    /* Wire body after the 24-byte command header: 8-byte COM handle id
     * + 8-byte array_count(=0) + 4-byte SampleMask. */
    const size_t hdr = sizeof(struct npt_command_header);
    const uint64_t *body = (const uint64_t *)(buf + hdr);
    if (cmd_size != hdr + 8 + 8 + 4) {
        fprintf(stderr, "FAIL: OMSetBlendState NULL: cmd_size=%zu, expected %zu\n",
                cmd_size, hdr + 8 + 8 + 4);
        return -1;
    }
    if (body[1] != 0) {
        fprintf(stderr, "FAIL: OMSetBlendState NULL: array_count=%llu, expected 0\n",
                (unsigned long long)body[1]);
        return -1;
    }
    return 0;
}

static int test_guest_OMSetBlendFactor_null_BlendFactor(void)
{
    uint8_t buf[128] = {0};
    struct npt_cs_encoder enc = npt_test_encoder_init(buf, sizeof(buf));
    npt_encode_ID3D12GraphicsCommandList_OMSetBlendFactor(&enc, 0, 0xDEAD, NULL);
    size_t cmd_size = npt_test_encoder_written(&enc, buf);

    const size_t hdr = sizeof(struct npt_command_header);
    const uint64_t *body = (const uint64_t *)(buf + hdr);
    if (cmd_size != hdr + 8) {
        fprintf(stderr, "FAIL: OMSetBlendFactor NULL: cmd_size=%zu, expected %zu\n",
                cmd_size, hdr + 8);
        return -1;
    }
    if (body[0] != 0) {
        fprintf(stderr, "FAIL: OMSetBlendFactor NULL: array_count=%llu, expected 0\n",
                (unsigned long long)body[0]);
        return -1;
    }
    return 0;
}

/* ================================================================== */
/* Dispatch table                                                     */
/* ================================================================== */

typedef int (*guest_manual_test_func)(void);

struct guest_manual_test_entry {
    const char *name;
    guest_manual_test_func func;
};

static const struct guest_manual_test_entry guest_manual_tests[] = {
    { "guest encode ID3D11DeviceContext::OMSetBlendState NULL BlendFactor",
      test_guest_OMSetBlendState_null_BlendFactor },
    { "guest encode ID3D12GraphicsCommandList::OMSetBlendFactor NULL BlendFactor",
      test_guest_OMSetBlendFactor_null_BlendFactor },
};

#define GUEST_MANUAL_TEST_COUNT \
    (int)(sizeof(guest_manual_tests) / sizeof(guest_manual_tests[0]))

int npt_guest_manual_test_count(void)
{
    return GUEST_MANUAL_TEST_COUNT;
}

int npt_guest_manual_test_run(int index)
{
    if (index < 0 || index >= GUEST_MANUAL_TEST_COUNT)
        return -1;
    return guest_manual_tests[index].func();
}

const char *npt_guest_manual_test_name(int index)
{
    if (index < 0 || index >= GUEST_MANUAL_TEST_COUNT)
        return "(invalid)";
    return guest_manual_tests[index].name;
}

#pragma GCC diagnostic pop
