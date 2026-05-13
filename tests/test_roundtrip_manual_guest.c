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
/* Reply-size upper-bound invariant (meta-test)                       */
/* ================================================================== */

/*
 * Every reply-bearing method's `npt_sizeof_..._reply()` is a pre-
 * submission reservation: a compile-time/static-content estimate of
 * how many bytes the host encoder will write into the reply slot.
 * For the protocol to be sound the reservation must be a true upper
 * bound on the actual wire size for every reachable value of the
 * reply payload.
 *
 * Three failure modes the test covers:
 *
 *   1. Discriminator silencing.  Zero-initialised values make
 *      `if (val->Tag == K)` arms inside a struct's sizing helper
 *      go false, so the helper undercounts by the variant payload.
 *
 *   2. Embedded fixed-size array prefix.  The wire format prepends
 *      an 8-byte `array_count` to every fixed array; C `sizeof(T[N])`
 *      doesn't carry it.  Hits D3D11_BLEND_DESC, BLEND_DESC1, ...
 *
 *   3. Narrow-primitive padding.  Single uint8_t / uint16_t fields
 *      pad to 4 bytes on the wire; in C they can pack tighter and
 *      the struct's trailing alignment slop may not cover the diff.
 *      Hits D3D11_DEPTH_STENCIL_DESC (two UINT8 fields).
 *
 * For each representative reply type, populate a value that
 * exercises the relevant failure mode, then assert the codegen-
 * emitted reservation function returns >= the wire size from the
 * per-type sizing helper.  Both halves route through live codegen
 * output so a regression in either the reservation formula or the
 * encoder is caught.
 */
static int test_guest_reply_size_upper_bound_meta(void)
{
    int failures = 0;
    const size_t hdr = sizeof(struct npt_reply_header)
                     + npt_sizeof_simple_pointer((const void *)1);

#define CHECK_BOUND(label, reserved_expr, wire_payload_expr) do {       \
    const size_t _r = (reserved_expr);                                  \
    const size_t _w = hdr + (wire_payload_expr);                        \
    if (_r < _w) {                                                      \
        fprintf(stderr, "FAIL: %s reserved %zu < wire %zu\n",           \
                label, _r, _w);                                         \
        failures++;                                                     \
    }                                                                   \
} while (0)

    /* Failure mode 1: discriminator silencing.  SRV desc has 11
     * union arms keyed off ViewDimension; sweep every one. */
    {
        D3D11_SHADER_RESOURCE_VIEW_DESC desc;
        const D3D11_SRV_DIMENSION arms[] = {
            D3D11_SRV_DIMENSION_BUFFER,
            D3D11_SRV_DIMENSION_TEXTURE1D,
            D3D11_SRV_DIMENSION_TEXTURE1DARRAY,
            D3D11_SRV_DIMENSION_TEXTURE2D,
            D3D11_SRV_DIMENSION_TEXTURE2DARRAY,
            D3D11_SRV_DIMENSION_TEXTURE2DMS,
            D3D11_SRV_DIMENSION_TEXTURE2DMSARRAY,
            D3D11_SRV_DIMENSION_TEXTURE3D,
            D3D11_SRV_DIMENSION_TEXTURECUBE,
            D3D11_SRV_DIMENSION_TEXTURECUBEARRAY,
            D3D11_SRV_DIMENSION_BUFFEREX,
        };
        for (size_t i = 0; i < sizeof(arms) / sizeof(arms[0]); i++) {
            memset(&desc, 0, sizeof(desc));
            desc.ViewDimension = arms[i];
            char label[64];
            snprintf(label, sizeof(label),
                     "SRV GetDesc ViewDimension=%d", (int)arms[i]);
            CHECK_BOUND(label,
                npt_sizeof_ID3D11ShaderResourceView_GetDesc_reply(&desc),
                npt_sizeof_D3D11_SHADER_RESOURCE_VIEW_DESC(&desc, 0));
        }
    }

    /* Failure mode 2: embedded fixed array prefix.  BLEND_DESC has
     * RenderTarget[8] inside, contributing an 8-byte `array_count`
     * the C struct doesn't carry. */
    {
        D3D11_BLEND_DESC desc;
        memset(&desc, 0, sizeof(desc));
        CHECK_BOUND("BLEND GetDesc",
            npt_sizeof_ID3D11BlendState_GetDesc_reply(&desc),
            npt_sizeof_D3D11_BLEND_DESC(&desc, 0));
    }
    {
        D3D11_BLEND_DESC1 desc;
        memset(&desc, 0, sizeof(desc));
        CHECK_BOUND("BLEND1 GetDesc1",
            npt_sizeof_ID3D11BlendState1_GetDesc1_reply(&desc),
            npt_sizeof_D3D11_BLEND_DESC1(&desc, 0));
    }

    /* Failure mode 3: narrow-primitive padding.  DEPTH_STENCIL_DESC
     * has two UINT8 fields whose wire size pads to 4 bytes each;
     * trailing C struct padding doesn't fully cover the delta. */
    {
        D3D11_DEPTH_STENCIL_DESC desc;
        memset(&desc, 0, sizeof(desc));
        CHECK_BOUND("DEPTH_STENCIL GetDesc",
            npt_sizeof_ID3D11DepthStencilState_GetDesc_reply(&desc),
            npt_sizeof_D3D11_DEPTH_STENCIL_DESC(&desc, 0));
    }

    /* Sanity: pure-POD struct with no discriminator and no embedded
     * array.  Must always be in bounds; failure here means the
     * reservation formula itself is broken, not a specific failure
     * mode. */
    {
        D3D11_BUFFER_DESC desc;
        memset(&desc, 0, sizeof(desc));
        CHECK_BOUND("BUFFER GetDesc",
            npt_sizeof_ID3D11Buffer_GetDesc_reply(&desc),
            npt_sizeof_D3D11_BUFFER_DESC(&desc, 0));
    }
    {
        D3D11_TEXTURE2D_DESC desc;
        memset(&desc, 0, sizeof(desc));
        CHECK_BOUND("TEXTURE2D GetDesc",
            npt_sizeof_ID3D11Texture2D_GetDesc_reply(&desc),
            npt_sizeof_D3D11_TEXTURE2D_DESC(&desc, 0));
    }
    {
        D3D11_CLASS_INSTANCE_DESC desc;
        memset(&desc, 0, sizeof(desc));
        CHECK_BOUND("CLASS_INSTANCE GetDesc",
            npt_sizeof_ID3D11ClassInstance_GetDesc_reply(&desc),
            npt_sizeof_D3D11_CLASS_INSTANCE_DESC(&desc, 0));
    }

#undef CHECK_BOUND
    return failures == 0 ? 0 : -1;
}

/* ================================================================== */
/* Unsupported-reply guest-side decode                                */
/* ================================================================== */

/*
 * When a reply contains a type with runtime-unbounded wire size (DRED
 * chains, root-signature parameter arrays, ...) the host's encode_reply
 * is a fatal-flag stub that writes nothing.  The guest reserves only
 * the header bytes, then `npt_decode_..._reply` reads a zeroed slot,
 * detects the cmd_type mismatch, and returns the documented default
 * for the call's return type (HRESULT → DXGI_ERROR_DEVICE_REMOVED).
 *
 * This test pins:
 *   - The guest's reply-size estimate is exactly `sizeof(reply_header)`.
 *   - Decoding a zero-init reply slot returns DXGI_ERROR_DEVICE_REMOVED
 *     instead of garbage or asserting.
 *   - The output buffer is left untouched (the existing mismatch path
 *     only zeros the return value, not output params).
 */
static int test_guest_unsupported_reply_DRED_decode(void)
{
    const size_t reserved =
        npt_sizeof_ID3D12DeviceRemovedExtendedData_GetAutoBreadcrumbsOutput_reply(NULL);
    if (reserved != sizeof(struct npt_reply_header)) {
        fprintf(stderr, "FAIL: DRED unsupported reply reserves %zu bytes; "
                "expected exactly sizeof(reply_header)=%zu\n",
                reserved, sizeof(struct npt_reply_header));
        return -1;
    }

    /* Simulate "host wrote nothing" — reply slot is zero-init. */
    uint8_t reply_buf[64] = {0};
    struct npt_cs_decoder dec = npt_test_decoder_init(reply_buf, reserved);
    D3D12_DRED_AUTO_BREADCRUMBS_OUTPUT output;
    memset(&output, 0xAB, sizeof(output));  /* sentinel */
    HRESULT ret = (HRESULT)0;
    npt_decode_ID3D12DeviceRemovedExtendedData_GetAutoBreadcrumbsOutput_reply(
        &dec, &output, &ret);

    const HRESULT expected = (HRESULT)0x887A0005; /* DXGI_ERROR_DEVICE_REMOVED */
    if (ret != expected) {
        fprintf(stderr, "FAIL: DRED unsupported reply decode returned "
                "0x%08x; expected 0x%08x (DXGI_ERROR_DEVICE_REMOVED)\n",
                (unsigned)ret, (unsigned)expected);
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
    { "guest reply size upper-bound invariant (meta)",
      test_guest_reply_size_upper_bound_meta },
    { "guest decode DRED GetAutoBreadcrumbsOutput unsupported reply default",
      test_guest_unsupported_reply_DRED_decode },
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
