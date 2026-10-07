/*
 * Copyright 2026 Turing Software LLC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Manual roundtrip tests for struct types skipped by npt_testgen.py.
 *
 * These structs contain anonymous unions whose variants are ALL encoded
 * by the generated codec.  Because the union variants share memory, the
 * automated initializer cannot safely fill them.  We test each variant
 * manually, ensuring inactive variant pointer fields remain NULL (zeroed)
 * so the encoder does not dereference garbage pointers.
 */

#include "npt_cs.h"
#include "npt_protocol_host.h"
#include "npt_test_harness.h"

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

/* ================================================================== */
/* NOT TESTABLE -- listed for completeness                            */
/* ================================================================== */
/*
 * The following structs contain void* fields without a count.  The codec
 * either skips them or returns 0 from sizeof.  No roundtrip is possible.
 *
 *   D3D11_SUBRESOURCE_DATA           (void *pSysMem)
 *   D3D11_MAPPED_SUBRESOURCE         (void *pData)
 *   D3D12_STATE_SUBOBJECT            (void *pDesc)
 *   D3D12_NODE_CPU_INPUT             (void *pRecords)
 *   D3D12_SUBRESOURCE_DATA           (void *pData)
 *   D3D12_MEMCPY_DEST                (void *pData)
 *
 * D3D12_PIPELINE_STATE_STREAM_DESC (_Inexpressible_ count) has a
 * hand-written codec (manual_codec) and is tested below.
 *
 * Transitively non-serializable:
 *   D3D12_STATE_OBJECT_DESC          -> D3D12_STATE_SUBOBJECT
 *   D3D12_SUBOBJECT_TO_EXPORTS_ASSOCIATION -> D3D12_STATE_SUBOBJECT
 *   D3D12_GENERIC_PROGRAM_DESC       -> D3D12_STATE_SUBOBJECT
 *   D3D12_MULTI_NODE_CPU_INPUT       -> D3D12_NODE_CPU_INPUT
 *   D3D12_DISPATCH_GRAPH_DESC        -> D3D12_NODE_CPU_INPUT
 *   D3D12_NODE / D3D12_SHADER_NODE   -> D3D12_NODE_CPU_INPUT
 *
 * Encoder returns 0 / sets fatal:
 *   D3D12_BUILD_RAYTRACING_ACCELERATION_STRUCTURE_INPUTS
 *       -> ppGeometryDescs is unsized and not optional
 */

/* ================================================================== */
/* Helpers                                                            */
/* ================================================================== */

/*
 * Allocate a zero-filled buffer large enough for `count` elements of size
 * `largest_variant_size`.  The encoder reads all union variants from the
 * same memory; the buffer must be large enough for the largest variant
 * to avoid out-of-bounds reads.
 */
static void *
alloc_union_array(size_t count, size_t largest_variant_size)
{
    return npt_test_alloc(count * largest_variant_size);
}

/* ================================================================== */
/* Test functions                                                     */
/* ================================================================== */

/* ------------------------------------------------------------------ */
/* D3D11_AUTHENTICATED_PROTECTION_FLAGS                               */
/*   union { struct { bitfields } Flags; UINT Value; }                */
/* ------------------------------------------------------------------ */

static int test_manual_D3D11_AUTHENTICATED_PROTECTION_FLAGS_Value(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D11_AUTHENTICATED_PROTECTION_FLAGS orig;
    memset(&orig, 0, sizeof(orig));
    /* Set Value; Flags bitfields alias the same memory. */
    orig.Value = npt_test_rand(&seed) & 0xFFu;

    size_t w1_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D11_AUTHENTICATED_PROTECTION_FLAGS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D11_AUTHENTICATED_PROTECTION_FLAGS (Value)", w1, w1_actual,
        w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

static int test_manual_D3D11_AUTHENTICATED_PROTECTION_FLAGS_Flags(void)
{
    D3D11_AUTHENTICATED_PROTECTION_FLAGS orig;
    memset(&orig, 0, sizeof(orig));
    orig.Flags.ProtectionEnabled = 1;
    orig.Flags.OverlayOrFullscreenRequired = 1;
    orig.Flags.Reserved = 42;

    size_t w1_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D11_AUTHENTICATED_PROTECTION_FLAGS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D11_AUTHENTICATED_PROTECTION_FLAGS (Flags)", w1, w1_actual,
        w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_RESOURCE_BARRIER                                             */
/*   struct { Type, Flags; union { Transition, Aliasing, UAV } }      */
/*                                                                    */
/*   All three variant pointers (pResource handles in sub-structs)    */
/*   share the same union memory.  We zero-init the union and only    */
/*   fill the active variant's fields.  The other variants' handle    */
/*   fields read zeros, which encode as object_id 0.                  */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_RESOURCE_BARRIER_Transition(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_RESOURCE_BARRIER orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    orig.Flags = D3D12_RESOURCE_BARRIER_FLAG_NONE;
    orig.Transition.pResource = npt_test_handle_create(&seed);
    orig.Transition.Subresource = npt_test_rand(&seed) & 0xF;
    orig.Transition.StateBefore = D3D12_RESOURCE_STATE_COMMON;
    orig.Transition.StateAfter = D3D12_RESOURCE_STATE_RENDER_TARGET;

    size_t w1_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RESOURCE_BARRIER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RESOURCE_BARRIER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_RESOURCE_BARRIER (Transition)", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

static int test_manual_D3D12_RESOURCE_BARRIER_Aliasing(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_RESOURCE_BARRIER orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_RESOURCE_BARRIER_TYPE_ALIASING;
    orig.Flags = D3D12_RESOURCE_BARRIER_FLAG_NONE;
    orig.Aliasing.pResourceBefore = npt_test_handle_create(&seed);
    orig.Aliasing.pResourceAfter = npt_test_handle_create(&seed);

    size_t w1_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RESOURCE_BARRIER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RESOURCE_BARRIER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_RESOURCE_BARRIER (Aliasing)", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

static int test_manual_D3D12_RESOURCE_BARRIER_UAV(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_RESOURCE_BARRIER orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
    orig.Flags = D3D12_RESOURCE_BARRIER_FLAG_NONE;
    orig.UAV.pResource = npt_test_handle_create(&seed);

    size_t w1_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RESOURCE_BARRIER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RESOURCE_BARRIER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_RESOURCE_BARRIER (UAV)", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_ROOT_PARAMETER                                               */
/*   struct { ParameterType; union { DescriptorTable, Constants,      */
/*            Descriptor }; ShaderVisibility }                        */
/*                                                                    */
/*   DescriptorTable contains pDescriptorRanges (pointer).  When      */
/*   testing Constants or Descriptor variants, the union must remain   */
/*   zeroed at the pointer field offset to keep pDescriptorRanges      */
/*   NULL.  We fill only non-pointer scalars in the chosen variant.   */
/* ------------------------------------------------------------------ */

/*
 * Helper: init a D3D12_ROOT_PARAMETER with Constants variant.
 * Constants.Num32BitValues is at the same offset as the lower bytes
 * of DescriptorTable.pDescriptorRanges on 64-bit.  We must keep it 0.
 */
static void
init_root_param_constants(D3D12_ROOT_PARAMETER *p, uint32_t *seed)
{
    memset(p, 0, sizeof(*p));
    p->ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    p->Constants.ShaderRegister = npt_test_rand(seed) & 0xF;
    p->Constants.RegisterSpace = npt_test_rand(seed) & 0xF;
    /* Num32BitValues must be 0: it aliases pDescriptorRanges low bytes */
    p->Constants.Num32BitValues = 0;
    p->ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL;
}

static int test_manual_D3D12_ROOT_PARAMETER_Constants(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_ROOT_PARAMETER orig;
    init_root_param_constants(&orig, &seed);

    size_t w1_size = npt_sizeof_D3D12_ROOT_PARAMETER(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_PARAMETER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_PARAMETER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_PARAMETER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_PARAMETER(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_PARAMETER(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_ROOT_PARAMETER (Constants)", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

static int test_manual_D3D12_ROOT_PARAMETER_DescriptorTable(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_ROOT_PARAMETER orig;
    memset(&orig, 0, sizeof(orig));
    orig.ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    orig.ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;

    /* Allocate 1 descriptor range */
    D3D12_DESCRIPTOR_RANGE *ranges = (D3D12_DESCRIPTOR_RANGE *)
        npt_test_alloc(1 * sizeof(D3D12_DESCRIPTOR_RANGE));
    npt_test_fill(ranges, sizeof(D3D12_DESCRIPTOR_RANGE), &seed);
    orig.DescriptorTable.NumDescriptorRanges = 1;
    orig.DescriptorTable.pDescriptorRanges = ranges;

    size_t w1_size = npt_sizeof_D3D12_ROOT_PARAMETER(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_PARAMETER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_PARAMETER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_PARAMETER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_PARAMETER(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_PARAMETER(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_ROOT_PARAMETER (DescriptorTable)",
        w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_ROOT_PARAMETER1 (same layout, uses DESCRIPTOR_RANGE1)        */
/* ------------------------------------------------------------------ */

static void
init_root_param1_constants(D3D12_ROOT_PARAMETER1 *p, uint32_t *seed)
{
    memset(p, 0, sizeof(*p));
    p->ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    p->Constants.ShaderRegister = npt_test_rand(seed) & 0xF;
    p->Constants.RegisterSpace = npt_test_rand(seed) & 0xF;
    p->Constants.Num32BitValues = 0; /* aliases pDescriptorRanges */
    p->ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL;
}

static int test_manual_D3D12_ROOT_PARAMETER1_Constants(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_ROOT_PARAMETER1 orig;
    init_root_param1_constants(&orig, &seed);

    size_t w1_size = npt_sizeof_D3D12_ROOT_PARAMETER1(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_PARAMETER1(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_PARAMETER1 decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_PARAMETER1(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_PARAMETER1(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_PARAMETER1(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_ROOT_PARAMETER1 (Constants)", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_ROOT_SIGNATURE_DESC                                          */
/*   Uses D3D12_ROOT_PARAMETER with Constants variant (safest).       */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_ROOT_SIGNATURE_DESC(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_ROOT_SIGNATURE_DESC orig;
    memset(&orig, 0, sizeof(orig));

    /* 1 root parameter (Constants variant) */
    D3D12_ROOT_PARAMETER *params = (D3D12_ROOT_PARAMETER *)
        npt_test_alloc(1 * sizeof(D3D12_ROOT_PARAMETER));
    init_root_param_constants(&params[0], &seed);
    orig.NumParameters = 1;
    orig.pParameters = params;

    /* No static samplers */
    orig.NumStaticSamplers = 0;
    orig.pStaticSamplers = NULL;
    orig.Flags = D3D12_ROOT_SIGNATURE_FLAG_NONE;

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_ROOT_SIGNATURE_DESC", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_ROOT_SIGNATURE_DESC1                                         */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_ROOT_SIGNATURE_DESC1(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_ROOT_SIGNATURE_DESC1 orig;
    memset(&orig, 0, sizeof(orig));

    D3D12_ROOT_PARAMETER1 *params = (D3D12_ROOT_PARAMETER1 *)
        npt_test_alloc(1 * sizeof(D3D12_ROOT_PARAMETER1));
    init_root_param1_constants(&params[0], &seed);
    orig.NumParameters = 1;
    orig.pParameters = params;
    orig.NumStaticSamplers = 0;
    orig.pStaticSamplers = NULL;
    orig.Flags = D3D12_ROOT_SIGNATURE_FLAG_NONE;

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC1(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC1(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC1 decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC1(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC1(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC1(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_ROOT_SIGNATURE_DESC1", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_ROOT_SIGNATURE_DESC2                                         */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_ROOT_SIGNATURE_DESC2(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_ROOT_SIGNATURE_DESC2 orig;
    memset(&orig, 0, sizeof(orig));

    D3D12_ROOT_PARAMETER1 *params = (D3D12_ROOT_PARAMETER1 *)
        npt_test_alloc(1 * sizeof(D3D12_ROOT_PARAMETER1));
    init_root_param1_constants(&params[0], &seed);
    orig.NumParameters = 1;
    orig.pParameters = params;
    orig.NumStaticSamplers = 0;
    orig.pStaticSamplers = NULL;
    orig.Flags = D3D12_ROOT_SIGNATURE_FLAG_NONE;

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC2(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC2(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC2 decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC2(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC2(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC2(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_ROOT_SIGNATURE_DESC2", w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_VERSIONED_ROOT_SIGNATURE_DESC                                */
/*   struct { Version; union { Desc_1_0, Desc_1_1, Desc_1_2 } }      */
/*                                                                    */
/*   All three Desc variants are encoded.  Each contains pParameters  */
/*   and pStaticSamplers arrays.  When initializing one variant, the  */
/*   other variants' pParameters/pStaticSamplers alias the same union */
/*   memory, so they must also be valid (or NULL).                    */
/*                                                                    */
/*   Safest: zero-init the whole union (all pointer fields NULL),     */
/*   then set only the chosen variant's pParameters to a valid array  */
/*   of Constants-variant root parameters.  The other variants'       */
/*   pParameters fields alias the same pointer, and since all three   */
/*   Desc layouts begin with {NumParameters, pParameters, ...},       */
/*   they all point to the same valid array.                          */
/*                                                                    */
/*   Note: Desc_1_0 uses D3D12_ROOT_PARAMETER, Desc_1_1/1_2 use      */
/*   D3D12_ROOT_PARAMETER1.  The union memory is shared, so the      */
/*   pointer points to the SAME allocation regardless of which type   */
/*   the encoder thinks it is.  For Constants variant (all scalars),  */
/*   D3D12_ROOT_PARAMETER and D3D12_ROOT_PARAMETER1 have the same    */
/*   layout for {ParameterType, Constants, ShaderVisibility} so       */
/*   the wire bytes match.  Similarly for the pStaticSamplers fields: */
/*   they are all NULL (no static samplers), so the encoder writes    */
/*   count=0 for each.                                                */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_VERSIONED_ROOT_SIGNATURE_DESC_1_0(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_VERSIONED_ROOT_SIGNATURE_DESC orig;
    memset(&orig, 0, sizeof(orig));
    orig.Version = D3D_ROOT_SIGNATURE_VERSION_1_0;

    /*
     * Allocate root params large enough for the larger of
     * D3D12_ROOT_PARAMETER / D3D12_ROOT_PARAMETER1 since the other
     * desc variants alias this pointer and interpret it as their type.
     */
    size_t param_size = sizeof(D3D12_ROOT_PARAMETER) > sizeof(D3D12_ROOT_PARAMETER1)
                      ? sizeof(D3D12_ROOT_PARAMETER)
                      : sizeof(D3D12_ROOT_PARAMETER1);
    void *param_buf = npt_test_alloc(param_size);
    memset(param_buf, 0, param_size);
    init_root_param_constants((D3D12_ROOT_PARAMETER *)param_buf, &seed);

    orig.Desc_1_0.NumParameters = 1;
    orig.Desc_1_0.pParameters = (const D3D12_ROOT_PARAMETER *)param_buf;
    orig.Desc_1_0.NumStaticSamplers = 0;
    orig.Desc_1_0.pStaticSamplers = NULL;
    orig.Desc_1_0.Flags = D3D12_ROOT_SIGNATURE_FLAG_NONE;

    size_t w1_size = npt_sizeof_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_VERSIONED_ROOT_SIGNATURE_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_VERSIONED_ROOT_SIGNATURE_DESC (v1.0)",
        w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_BARRIER_GROUP                                                */
/*   struct { Type, NumBarriers; union { pGlobalBarriers,             */
/*            pTextureBarriers, pBufferBarriers } }                   */
/*                                                                    */
/*   All three pointer variants alias the same memory.  We allocate   */
/*   a buffer large enough for the largest variant type and zero-fill */
/*   it, then populate only the active variant's fields.              */
/* ------------------------------------------------------------------ */

/*
 * D3D12_BARRIER_GROUP: The anonymous union means encode produces wire data for
 * ALL three variant arrays from the SAME memory.  After decode the decoder
 * allocates separate buffers, so a full wire roundtrip is not idempotent.
 * Instead we verify the active variant's element data survives encode→decode.
 */
static int test_manual_D3D12_BARRIER_GROUP_Global(void)
{
    D3D12_BARRIER_GROUP orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_BARRIER_TYPE_GLOBAL;
    orig.NumBarriers = 1;

    size_t max_variant = sizeof(D3D12_TEXTURE_BARRIER);
    void *buf = alloc_union_array(1, max_variant);
    D3D12_GLOBAL_BARRIER *gb = (D3D12_GLOBAL_BARRIER *)buf;
    gb->SyncBefore = D3D12_BARRIER_SYNC_ALL;
    gb->SyncAfter = D3D12_BARRIER_SYNC_ALL;
    gb->AccessBefore = D3D12_BARRIER_ACCESS_COMMON;
    gb->AccessAfter = D3D12_BARRIER_ACCESS_COMMON;
    orig.pGlobalBarriers = gb;

    size_t w1_size = npt_sizeof_D3D12_BARRIER_GROUP(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_BARRIER_GROUP(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_BARRIER_GROUP decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_BARRIER_GROUP(&dec, &decoded);

    /* Verify active variant data */
    int result = 0;
    if (decoded.NumBarriers != 1 ||
        !decoded.pGlobalBarriers ||
        memcmp(gb, decoded.pGlobalBarriers, sizeof(D3D12_GLOBAL_BARRIER)) != 0) {
        fprintf(stderr, "FAIL: D3D12_BARRIER_GROUP (Global): active variant mismatch\n");
        result = -1;
    }
    npt_test_cleanup(&dec);
    free(w1);
    return result;
}

static int test_manual_D3D12_BARRIER_GROUP_Texture(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_BARRIER_GROUP orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_BARRIER_TYPE_TEXTURE;
    orig.NumBarriers = 1;

    size_t max_variant = sizeof(D3D12_TEXTURE_BARRIER);
    void *buf = alloc_union_array(1, max_variant);
    D3D12_TEXTURE_BARRIER *tb = (D3D12_TEXTURE_BARRIER *)buf;
    tb->SyncBefore = D3D12_BARRIER_SYNC_ALL;
    tb->SyncAfter = D3D12_BARRIER_SYNC_ALL;
    tb->AccessBefore = D3D12_BARRIER_ACCESS_COMMON;
    tb->AccessAfter = D3D12_BARRIER_ACCESS_COMMON;
    tb->LayoutBefore = D3D12_BARRIER_LAYOUT_COMMON;
    tb->LayoutAfter = D3D12_BARRIER_LAYOUT_COMMON;
    tb->pResource = npt_test_handle_create(&seed);
    memset(&tb->Subresources, 0, sizeof(tb->Subresources));
    tb->Flags = D3D12_TEXTURE_BARRIER_FLAG_NONE;
    orig.pTextureBarriers = tb;

    size_t w1_size = npt_sizeof_D3D12_BARRIER_GROUP(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_BARRIER_GROUP(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_BARRIER_GROUP decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_BARRIER_GROUP(&dec, &decoded);

    /* Compare active variant element data (handles become identity IDs) */
    int result = 0;
    if (decoded.NumBarriers != 1 || !decoded.pTextureBarriers) {
        fprintf(stderr, "FAIL: D3D12_BARRIER_GROUP (Texture): decode count/ptr\n");
        result = -1;
    } else {
        /* Compare fields that survive the multi-variant encode.
         * Subresources may be corrupted by other variants reading
         * the same union memory as different struct types. */
        const D3D12_TEXTURE_BARRIER *dt = decoded.pTextureBarriers;
        if (dt->SyncBefore != tb->SyncBefore ||
            dt->SyncAfter != tb->SyncAfter ||
            dt->AccessBefore != tb->AccessBefore ||
            dt->AccessAfter != tb->AccessAfter) {
            fprintf(stderr, "FAIL: D3D12_BARRIER_GROUP (Texture): field mismatch\n");
            result = -1;
        }
    }
    npt_test_cleanup(&dec);
    free(w1);
    return result;
}

static int test_manual_D3D12_BARRIER_GROUP_Buffer(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_BARRIER_GROUP orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_BARRIER_TYPE_BUFFER;
    orig.NumBarriers = 1;

    size_t max_variant = sizeof(D3D12_TEXTURE_BARRIER);
    void *buf = alloc_union_array(1, max_variant);
    D3D12_BUFFER_BARRIER *bb = (D3D12_BUFFER_BARRIER *)buf;
    bb->SyncBefore = D3D12_BARRIER_SYNC_ALL;
    bb->SyncAfter = D3D12_BARRIER_SYNC_ALL;
    bb->AccessBefore = D3D12_BARRIER_ACCESS_COMMON;
    bb->AccessAfter = D3D12_BARRIER_ACCESS_COMMON;
    bb->pResource = npt_test_handle_create(&seed);
    bb->Offset = 0;
    bb->Size = 256;
    orig.pBufferBarriers = bb;

    size_t w1_size = npt_sizeof_D3D12_BARRIER_GROUP(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_BARRIER_GROUP(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_BARRIER_GROUP decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_BARRIER_GROUP(&dec, &decoded);

    int result = 0;
    if (decoded.NumBarriers != 1 || !decoded.pBufferBarriers) {
        fprintf(stderr, "FAIL: D3D12_BARRIER_GROUP (Buffer): decode count/ptr\n");
        result = -1;
    } else {
        const D3D12_BUFFER_BARRIER *db = decoded.pBufferBarriers;
        if (db->SyncBefore != bb->SyncBefore ||
            db->SyncAfter != bb->SyncAfter ||
            db->AccessBefore != bb->AccessBefore ||
            db->AccessAfter != bb->AccessAfter ||
            db->Offset != bb->Offset ||
            db->Size != bb->Size) {
            fprintf(stderr, "FAIL: D3D12_BARRIER_GROUP (Buffer): field mismatch\n");
            result = -1;
        }
    }
    npt_test_cleanup(&dec);
    free(w1);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_RENDER_PASS_ENDING_ACCESS                                    */
/*   struct { Type; union { Resolve, PreserveLocal } }                */
/*                                                                    */
/*   Resolve has pSrcResource/pDstResource handles and a              */
/*   pSubresourceParameters counted array.  PreserveLocal has only    */
/*   scalar fields.  Both variants are always encoded.                */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_RENDER_PASS_ENDING_ACCESS_Preserve(void)
{
    D3D12_RENDER_PASS_ENDING_ACCESS orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_RENDER_PASS_ENDING_ACCESS_TYPE_PRESERVE;
    /* Resolve pointers are NULL (overlapping memory, zeroed by memset).
     * Set non-zero PreserveLocal values to verify data survives. */
    orig.PreserveLocal.AdditionalWidth = 640;
    orig.PreserveLocal.AdditionalHeight = 480;

    size_t w1_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RENDER_PASS_ENDING_ACCESS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RENDER_PASS_ENDING_ACCESS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RENDER_PASS_ENDING_ACCESS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_RENDER_PASS_ENDING_ACCESS(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_RENDER_PASS_ENDING_ACCESS (Preserve)",
        w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

static int test_manual_D3D12_RENDER_PASS_ENDING_ACCESS_Resolve(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    D3D12_RENDER_PASS_ENDING_ACCESS orig;
    memset(&orig, 0, sizeof(orig));
    orig.Type = D3D12_RENDER_PASS_ENDING_ACCESS_TYPE_RESOLVE;
    orig.Resolve.pSrcResource = npt_test_handle_create(&seed);
    orig.Resolve.pDstResource = npt_test_handle_create(&seed);
    orig.Resolve.SubresourceCount = 1;

    D3D12_RENDER_PASS_ENDING_ACCESS_RESOLVE_SUBRESOURCE_PARAMETERS *sub =
        (D3D12_RENDER_PASS_ENDING_ACCESS_RESOLVE_SUBRESOURCE_PARAMETERS *)
        npt_test_alloc(sizeof(*sub));
    npt_test_fill(sub, sizeof(*sub), &seed);
    orig.Resolve.pSubresourceParameters = sub;
    orig.Resolve.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    orig.Resolve.ResolveMode = D3D12_RESOLVE_MODE_AVERAGE;
    orig.Resolve.PreserveResolveSource = 0;

    size_t w1_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RENDER_PASS_ENDING_ACCESS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RENDER_PASS_ENDING_ACCESS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RENDER_PASS_ENDING_ACCESS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_RENDER_PASS_ENDING_ACCESS(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_RENDER_PASS_ENDING_ACCESS (Resolve)",
        w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ------------------------------------------------------------------ */
/* D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA                       */
/*   struct { Version; union { Dred_1_0, Dred_1_1, Dred_1_2,         */
/*            Dred_1_3 } }                                            */
/*                                                                    */
/*   All DRED variants contain pointers to linked-list nodes          */
/*   (AUTO_BREADCRUMB_NODE etc.).  With zero-init, all pointer fields */
/*   are NULL.  The encoder writes pointer-absent markers; the        */
/*   decoder sets fatal (but our test stub ignores that).  Wire       */
/*   bytes are deterministic regardless.                              */
/* ------------------------------------------------------------------ */

static int test_manual_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(void)
{
    D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA orig;
    memset(&orig, 0, sizeof(orig));
    orig.Version = D3D12_DRED_VERSION_1_0;
    /* Smoke test only: all DRED variants contain linked-list pointers
     * (pHeadAutoBreadcrumbNode, pHeadExistingStorageAutoBreadcrumbNode,
     * etc.) that reference self-referential types (pNext chains).
     * We test with all pointers NULL to verify the encoder handles
     * the NULL case without crashing. Deeper testing would require
     * hand-building linked lists of D3D12_AUTO_BREADCRUMB_NODE. */

    size_t w1_size = npt_sizeof_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    int result = npt_wire_compare(
        "D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA",
        w1, w1_actual, w2, w2_actual);
    npt_test_cleanup(&dec);
    free(w1); free(w2);
    return result;
}

/* ================================================================== */
/* Output-arg allocation tests (dispatcher decode -> reply encode)    */
/* ================================================================== */
/*
 * Cover the integration boundary the auto-generated roundtrip tests miss:
 * npt_decode_*_args_temp must allocate temp storage for every output-only
 * param so the reply encoder reads valid memory after the original D3D
 * call returns.  Each test builds a CMD wire, decodes it, asserts every
 * output arg points at decoder-owned storage, and drives the reply
 * encoder where it is sized.
 */

static int test_manual_dispatch_OMGetBlendState(void)
{
    /* CMD body: 1 uint64 guest_id for the output ppBlendState */
    uint8_t cmd_buf[64] = {0};
    struct npt_cs_encoder enc = npt_test_encoder_init(cmd_buf, sizeof(cmd_buf));
    uint64_t fake_gid = 0xdeadbeefcafef00dULL;
    npt_encode_uint64_t(&enc, &fake_gid);
    size_t cmd_size = npt_test_encoder_written(&enc, cmd_buf);

    struct npt_cs_decoder dec = npt_test_decoder_init(cmd_buf, cmd_size);
    struct npt_command_ID3D11DeviceContext_OMGetBlendState args = {0};
    npt_decode_ID3D11DeviceContext_OMGetBlendState_args_temp(&dec, &args);

    if (!args.ppBlendState || !args.BlendFactor || !args.pSampleMask) {
        fprintf(stderr, "FAIL: OMGetBlendState output args not all allocated "
                "(ppBlendState=%p BlendFactor=%p pSampleMask=%p)\n",
                (void *)args.ppBlendState, (void *)args.BlendFactor,
                (void *)args.pSampleMask);
        npt_test_cleanup(&dec);
        return -1;
    }
    if (args._guest_id_ppBlendState != fake_gid) {
        fprintf(stderr, "FAIL: OMGetBlendState guest_id not preserved\n");
        npt_test_cleanup(&dec);
        return -1;
    }

    /* Simulate dispatch filling the outputs, then drive the reply encoder. */
    args.BlendFactor[0] = 1.0f; args.BlendFactor[1] = 0.5f;
    args.BlendFactor[2] = 0.25f; args.BlendFactor[3] = 0.0f;
    *args.pSampleMask = 0xffffffffu;
    *args.ppBlendState = (ID3D11BlendState *)(uintptr_t)0xcafeULL;

    uint8_t reply_buf[128] = {0};
    struct npt_cs_encoder renc = npt_test_encoder_init(reply_buf, sizeof(reply_buf));
    npt_encode_ID3D11DeviceContext_OMGetBlendState_reply(&renc, &args);
    size_t reply_size = npt_test_encoder_written(&renc, reply_buf);

    /* reply header (16) + array_count(8) + 4*FLOAT(16) + simple_pointer(8) + UINT(4) */
    const size_t expected = sizeof(struct npt_reply_header) + 8 + 16 + 8 + 4;
    int result = (reply_size == expected) ? 0 : -1;
    if (result) {
        fprintf(stderr, "FAIL: OMGetBlendState reply size %zu != %zu\n",
                reply_size, expected);
    }
    npt_test_cleanup(&dec);
    return result;
}

static int test_manual_dispatch_GetDecoderBuffer(void)
{
    /* CMD body: uint64 pDecoder id + int32 Type enum */
    uint8_t cmd_buf[64] = {0};
    struct npt_cs_encoder enc = npt_test_encoder_init(cmd_buf, sizeof(cmd_buf));
    uint64_t fake_decoder = 0x1122334455667788ULL;
    npt_encode_uint64_t(&enc, &fake_decoder);
    int32_t buf_type = 0; /* D3D11_VIDEO_DECODER_BUFFER_PICTURE_PARAMETERS */
    npt_encode_int32_t(&enc, &buf_type);
    size_t cmd_size = npt_test_encoder_written(&enc, cmd_buf);

    struct npt_cs_decoder dec = npt_test_decoder_init(cmd_buf, cmd_size);
    struct npt_command_ID3D11VideoContext_GetDecoderBuffer args = {0};
    npt_decode_ID3D11VideoContext_GetDecoderBuffer_args_temp(&dec, &args);

    if (!args.pBufferSize || !args.ppBuffer) {
        fprintf(stderr, "FAIL: GetDecoderBuffer output args not all allocated "
                "(pBufferSize=%p ppBuffer=%p)\n",
                (void *)args.pBufferSize, (void *)args.ppBuffer);
        npt_test_cleanup(&dec);
        return -1;
    }

    /* *args.ppBuffer is NULL after alloc; reply encoder skips the data
     * loop in that case (count = *pBufferSize is also 0 from memset), so
     * encoding should produce a header + simple_pointer + UINT + count(0). */
    *args.pBufferSize = 0;
    uint8_t reply_buf[128] = {0};
    struct npt_cs_encoder renc = npt_test_encoder_init(reply_buf, sizeof(reply_buf));
    npt_encode_ID3D11VideoContext_GetDecoderBuffer_reply(&renc, &args);
    int result = (npt_test_encoder_written(&renc, reply_buf) > 0) ? 0 : -1;
    npt_test_cleanup(&dec);
    return result;
}

static int test_manual_dispatch_Map(void)
{
    /* CMD body: UINT Subresource + simple_pointer(=0) for pReadRange */
    uint8_t cmd_buf[64] = {0};
    struct npt_cs_encoder enc = npt_test_encoder_init(cmd_buf, sizeof(cmd_buf));
    UINT subresource = 0;
    npt_encode_UINT(&enc, &subresource);
    (void)npt_encode_simple_pointer(&enc, NULL); /* pReadRange = NULL */
    size_t cmd_size = npt_test_encoder_written(&enc, cmd_buf);

    struct npt_cs_decoder dec = npt_test_decoder_init(cmd_buf, cmd_size);
    struct npt_command_ID3D12Resource_Map args = {0};
    npt_decode_ID3D12Resource_Map_args_temp(&dec, &args);

    if (!args.ppData) {
        fprintf(stderr, "FAIL: Map ppData not allocated\n");
        npt_test_cleanup(&dec);
        return -1;
    }

    /* Simulate Map filling *ppData with a buffer address and exercise the
     * reply encoder (NULL-guarded simple_pointer + void*-as-uint64). */
    *args.ppData = (void *)(uintptr_t)0xfeedfaceULL;
    uint8_t reply_buf[64] = {0};
    struct npt_cs_encoder renc = npt_test_encoder_init(reply_buf, sizeof(reply_buf));
    npt_encode_ID3D12Resource_Map_reply(&renc, &args);
    int result = (npt_test_encoder_written(&renc, reply_buf) > 0) ? 0 : -1;
    npt_test_cleanup(&dec);
    return result;
}

static int test_manual_dispatch_GetRootSignatureDescAtVersion(void)
{
    /* CMD body: int32 convertToVersion enum */
    uint8_t cmd_buf[32] = {0};
    struct npt_cs_encoder enc = npt_test_encoder_init(cmd_buf, sizeof(cmd_buf));
    int32_t version = 1; /* D3D_ROOT_SIGNATURE_VERSION_1 */
    npt_encode_int32_t(&enc, &version);
    size_t cmd_size = npt_test_encoder_written(&enc, cmd_buf);

    struct npt_cs_decoder dec = npt_test_decoder_init(cmd_buf, cmd_size);
    struct npt_command_ID3D12VersionedRootSignatureDeserializer_GetRootSignatureDescAtVersion args = {0};
    npt_decode_ID3D12VersionedRootSignatureDeserializer_GetRootSignatureDescAtVersion_args_temp(
        &dec, &args);

    int result = args.ppDesc ? 0 : -1;
    if (result) {
        fprintf(stderr, "FAIL: GetRootSignatureDescAtVersion ppDesc not allocated\n");
    }
    /* Reply encoder is "unsized fatal" by design (encoder cannot serialize
     * a nested D3D12_VERSIONED_ROOT_SIGNATURE_DESC**); the dispatcher fix
     * only guarantees the dispatch decode path no longer hands a NULL
     * ppDesc to the original D3D12 call.  Don't drive the reply encoder. */
    npt_test_cleanup(&dec);
    return result;
}

/* Helper: build a CMD body shared by both root-signature-deserializer
 * top-level functions (same param shape).  Empty blob (count=0), zero
 * size, present IID with a recognisable pattern. */
static size_t build_root_sig_deserializer_cmd(uint8_t *buf, size_t buf_size)
{
    struct npt_cs_encoder enc = npt_test_encoder_init(buf, buf_size);
    npt_encode_array_count(&enc, 0); /* pSrcData blob: empty */
    uint64_t srcSize = 0;
    npt_encode_uint64_t(&enc, &srcSize); /* SrcDataSizeInBytes */
    (void)npt_encode_simple_pointer(&enc, (const void *)1); /* IID present */
    IID iid; memset(&iid, 0xAB, sizeof(iid));
    npt_encode_IID(&enc, &iid);
    return npt_test_encoder_written(&enc, buf);
}

static int test_manual_dispatch_D3D12CreateRootSignatureDeserializer(void)
{
    uint8_t cmd_buf[64] = {0};
    size_t cmd_size = build_root_sig_deserializer_cmd(cmd_buf, sizeof(cmd_buf));

    struct npt_cs_decoder dec = npt_test_decoder_init(cmd_buf, cmd_size);
    struct npt_command_D3D12CreateRootSignatureDeserializer args = {0};
    npt_decode_D3D12CreateRootSignatureDeserializer_args_temp(&dec, &args);

    int result = args.ppRootSignatureDeserializer ? 0 : -1;
    if (result) {
        fprintf(stderr, "FAIL: D3D12CreateRootSignatureDeserializer "
                "ppRootSignatureDeserializer not allocated\n");
    }
    npt_test_cleanup(&dec);
    return result;
}

static int test_manual_dispatch_D3D12CreateVersionedRootSignatureDeserializer(void)
{
    uint8_t cmd_buf[64] = {0};
    size_t cmd_size = build_root_sig_deserializer_cmd(cmd_buf, sizeof(cmd_buf));

    struct npt_cs_decoder dec = npt_test_decoder_init(cmd_buf, cmd_size);
    struct npt_command_D3D12CreateVersionedRootSignatureDeserializer args = {0};
    npt_decode_D3D12CreateVersionedRootSignatureDeserializer_args_temp(&dec, &args);

    int result = args.ppRootSignatureDeserializer ? 0 : -1;
    if (result) {
        fprintf(stderr, "FAIL: D3D12CreateVersionedRootSignatureDeserializer "
                "ppRootSignatureDeserializer not allocated\n");
    }
    npt_test_cleanup(&dec);
    return result;
}

/* ================================================================== */
/* Unsupported-reply gating                                           */
/* ================================================================== */

/*
 * Unsupported-reply gating: methods whose reply contains a type with
 * runtime-unbounded wire size (DRED chain pointers, root-signature
 * parameter arrays, ...) cannot fit in a pre-reserved fixed-size reply
 * slot.  The host's `npt_encode_..._reply` is generated as a fatal-flag
 * stub that writes nothing; the guest sees a zero reply header and
 * takes the documented-default branch in `npt_decode_..._reply`.
 *
 * Verify the host stub writes zero bytes (no header) for a DRED
 * method.  The complementary guest-side mismatch behaviour is covered
 * by `test_guest_unsupported_reply_DRED_decode` in
 * test_roundtrip_manual_guest.c.
 *
 * The reply-size *upper-bound* invariant (across every reply type with
 * a working reply path) is covered by the meta-test
 * `test_guest_reply_size_upper_bound_meta` on the guest side, since
 * `npt_sizeof_..._reply` is a guest-side helper.
 */
static int test_manual_reply_unsupported_encode_DRED(void)
{
    D3D12_DRED_AUTO_BREADCRUMBS_OUTPUT output;
    memset(&output, 0, sizeof(output));
    struct npt_command_ID3D12DeviceRemovedExtendedData_GetAutoBreadcrumbsOutput args = {0};
    args.pOutput = &output;
    args.ret = (HRESULT)0;

    uint8_t reply_buf[64];
    memset(reply_buf, 0xCC, sizeof(reply_buf));
    struct npt_cs_encoder renc = npt_test_encoder_init(reply_buf, sizeof(reply_buf));
    npt_encode_ID3D12DeviceRemovedExtendedData_GetAutoBreadcrumbsOutput_reply(
        &renc, &args);
    size_t actual = npt_test_encoder_written(&renc, reply_buf);

    if (actual != 0) {
        fprintf(stderr, "FAIL: DRED GetAutoBreadcrumbsOutput unsupported "
                "encode_reply wrote %zu bytes; expected 0 (fatal stub)\n",
                actual);
        return -1;
    }
    if (reply_buf[0] != 0xCC) {
        fprintf(stderr, "FAIL: DRED reply buffer modified despite fatal "
                "stub (first byte=0x%02x, expected 0xCC)\n", reply_buf[0]);
        return -1;
    }
    return 0;
}

/* ================================================================== */
/* Dispatch table                                                     */
/* ================================================================== */

typedef int (*manual_test_func)(void);

struct manual_test_entry {
    const char *name;
    manual_test_func func;
};

/* ------------------------------------------------------------------ */
/* D3D12_PIPELINE_STATE_STREAM_DESC (hand-written codec, manual_codec)  */
/* ------------------------------------------------------------------ */

/* Append one {type, payload} record laid out as
 * CD3DX12_PIPELINE_STATE_STREAM_SUBOBJECT lays it out. */
static void pss_put(uint8_t *buf, size_t *off, uint32_t type,
                    const void *payload, size_t size, size_t align)
{
    size_t at = (*off + sizeof(void *) - 1) & ~(sizeof(void *) - 1);
    memcpy(buf + at, &type, sizeof(type));
    at = (at + sizeof(type) + align - 1) & ~(align - 1);
    memcpy(buf + at, payload, size);
    *off = (at + size + sizeof(void *) - 1) & ~(sizeof(void *) - 1);
}

#define PSS_PUT(buf, off, tag, T, val) \
    pss_put(buf, off, D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_##tag, &(val), sizeof(T), _Alignof(T))

/* Encode `orig`, decode the wire, and check the decoded stream against
 * the original record by record: same types, same payload bytes (shader
 * bytecode compared by content since the decoded copy lives in decoder
 * memory), same SizeInBytes, and the decoded stream re-encodes to the
 * same wire bytes. */
static int pss_roundtrip(const char *name, const D3D12_PIPELINE_STATE_STREAM_DESC *orig,
                         int want_records)
{
    size_t w1_size = npt_sizeof_D3D12_PIPELINE_STATE_STREAM_DESC(orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_PIPELINE_STATE_STREAM_DESC(&enc1, orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);
    if (w1_actual != w1_size) {
        fprintf(stderr, "FAIL: %s: sizeof %zu, wrote %zu\n", name, w1_size, w1_actual);
        free(w1);
        return -1;
    }

    D3D12_PIPELINE_STATE_STREAM_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_PIPELINE_STATE_STREAM_DESC(&dec, &decoded);
    int result = 0;
    if (decoded.SizeInBytes != orig->SizeInBytes || !decoded.pPipelineStateSubobjectStream) {
        fprintf(stderr, "FAIL: %s: decoded size %zu (want %zu)\n", name,
                (size_t)decoded.SizeInBytes, (size_t)orig->SizeInBytes);
        result = -1;
    }

    const uint8_t *a = (const uint8_t *)orig->pPipelineStateSubobjectStream;
    const uint8_t *b = (const uint8_t *)decoded.pPipelineStateSubobjectStream;
    size_t pos = 0;
    int records = 0;
    while (result == 0 && pos < orig->SizeInBytes) {
        uint32_t ta, tb;
        size_t align, psize, poff;
        memcpy(&ta, a + pos, sizeof(ta));
        memcpy(&tb, b + pos, sizeof(tb));
        if (ta != tb) {
            fprintf(stderr, "FAIL: %s: record %d type %u vs %u\n", name, records, ta, tb);
            result = -1;
            break;
        }
        psize = npt_pss_payload((D3D12_PIPELINE_STATE_SUBOBJECT_TYPE)ta, &align);
        poff = (pos + sizeof(uint32_t) + align - 1) & ~(align - 1);
        if (ta == D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_ROOT_SIGNATURE) {
            /* the host keeps the guest id in the pointer slot until the
             * replace pass; the harness's npt_object_from_id is the identity */
            if (memcmp(a + poff, b + poff, psize) != 0) {
                fprintf(stderr, "FAIL: %s: record %d root signature id differs\n", name, records);
                result = -1;
                break;
            }
        } else if (ta == D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_MS ||
                   ta == D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_PS) {
            D3D12_SHADER_BYTECODE ba, bb;
            memcpy(&ba, a + poff, sizeof(ba));
            memcpy(&bb, b + poff, sizeof(bb));
            if (ba.BytecodeLength != bb.BytecodeLength ||
                (ba.BytecodeLength && (!bb.pShaderBytecode ||
                 memcmp(ba.pShaderBytecode, bb.pShaderBytecode, ba.BytecodeLength) != 0))) {
                fprintf(stderr, "FAIL: %s: record %d bytecode differs\n", name, records);
                result = -1;
                break;
            }
        } else if (memcmp(a + poff, b + poff, psize) != 0) {
            fprintf(stderr, "FAIL: %s: record %d payload differs\n", name, records);
            result = -1;
            break;
        }
        pos = (poff + psize + sizeof(void *) - 1) & ~(sizeof(void *) - 1);
        records++;
    }
    if (result == 0 && records != want_records) {
        fprintf(stderr, "FAIL: %s: %d records, want %d\n", name, records, want_records);
        result = -1;
    }

    if (result == 0) {
        size_t w2_size = npt_sizeof_D3D12_PIPELINE_STATE_STREAM_DESC(&decoded, 0);
        uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
        struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
        npt_encode_D3D12_PIPELINE_STATE_STREAM_DESC(&enc2, &decoded);
        size_t w2_actual = npt_test_encoder_written(&enc2, w2);
        result = npt_wire_compare(name, w1, w1_actual, w2, w2_actual);
        free(w2);
    }
    npt_test_cleanup(&dec);
    free(w1);
    return result;
}

/* A mesh pipeline as an app packs it: pointer-bearing payloads (root
 * signature handle, two shader blobs) among plain ones, with the 4- and
 * 8-byte-aligned payloads interleaved so every padding rule is exercised. */
static int test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_mesh(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    uint8_t ms_code[100], ps_code[52];
    for (size_t i = 0; i < sizeof(ms_code); i++) ms_code[i] = (uint8_t)npt_test_rand(&seed);
    for (size_t i = 0; i < sizeof(ps_code); i++) ps_code[i] = (uint8_t)npt_test_rand(&seed);

    _Alignas(void *) uint8_t stream[1024];
    memset(stream, 0xAB, sizeof(stream)); /* padding bytes are not part of the contract */
    size_t off = 0;
    ID3D12RootSignature *rs = (ID3D12RootSignature *)(uintptr_t)0x1234ULL;
    PSS_PUT(stream, &off, ROOT_SIGNATURE, ID3D12RootSignature *, rs);
    D3D12_SHADER_BYTECODE ms = { ms_code, sizeof(ms_code) };
    D3D12_SHADER_BYTECODE ps = { ps_code, sizeof(ps_code) };
    PSS_PUT(stream, &off, MS, D3D12_SHADER_BYTECODE, ms);
    PSS_PUT(stream, &off, PS, D3D12_SHADER_BYTECODE, ps);
    D3D12_BLEND_DESC blend; memset(&blend, 0, sizeof(blend));
    blend.RenderTarget[0].RenderTargetWriteMask = 0xF;
    blend.RenderTarget[3].BlendEnable = 1;
    PSS_PUT(stream, &off, BLEND, D3D12_BLEND_DESC, blend);
    UINT sample_mask = 0xFFFFFFFFu;
    PSS_PUT(stream, &off, SAMPLE_MASK, UINT, sample_mask);
    D3D12_RASTERIZER_DESC rast; memset(&rast, 0, sizeof(rast));
    rast.FillMode = D3D12_FILL_MODE_SOLID; rast.CullMode = D3D12_CULL_MODE_BACK; rast.DepthBias = 7;
    PSS_PUT(stream, &off, RASTERIZER, D3D12_RASTERIZER_DESC, rast);
    D3D12_DEPTH_STENCIL_DESC ds; memset(&ds, 0, sizeof(ds));
    ds.DepthEnable = 1; ds.DepthFunc = D3D12_COMPARISON_FUNC_LESS;
    PSS_PUT(stream, &off, DEPTH_STENCIL, D3D12_DEPTH_STENCIL_DESC, ds);
    D3D12_PRIMITIVE_TOPOLOGY_TYPE topo = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    PSS_PUT(stream, &off, PRIMITIVE_TOPOLOGY, D3D12_PRIMITIVE_TOPOLOGY_TYPE, topo);
    D3D12_RT_FORMAT_ARRAY rts; memset(&rts, 0, sizeof(rts));
    rts.NumRenderTargets = 2; rts.RTFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM; rts.RTFormats[1] = DXGI_FORMAT_R16G16_FLOAT;
    PSS_PUT(stream, &off, RENDER_TARGET_FORMATS, D3D12_RT_FORMAT_ARRAY, rts);
    DXGI_FORMAT dsv = DXGI_FORMAT_D32_FLOAT;
    PSS_PUT(stream, &off, DEPTH_STENCIL_FORMAT, DXGI_FORMAT, dsv);
    DXGI_SAMPLE_DESC sd = { 4, 0 };
    PSS_PUT(stream, &off, SAMPLE_DESC, DXGI_SAMPLE_DESC, sd);
    UINT node_mask = 1;
    PSS_PUT(stream, &off, NODE_MASK, UINT, node_mask);

    D3D12_PIPELINE_STATE_STREAM_DESC orig = { off, stream };
    return pss_roundtrip("D3D12_PIPELINE_STATE_STREAM_DESC (mesh)", &orig, 12);
}

/* Every record type in one stream, so each payload codec is reached. */
static int test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_all_records(void)
{
    uint32_t seed = 0xDEAD0000u + __LINE__;
    _Alignas(void *) uint8_t stream[2048];
    memset(stream, 0xCD, sizeof(stream));
    size_t off = 0;
    int records = 0;

    ID3D12RootSignature *rs = NULL;   /* a null root signature travels as id 0 */
    PSS_PUT(stream, &off, ROOT_SIGNATURE, ID3D12RootSignature *, rs); records++;
    D3D12_SHADER_BYTECODE empty = { NULL, 0 };
    PSS_PUT(stream, &off, VS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, PS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, DS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, HS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, GS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, CS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, AS, D3D12_SHADER_BYTECODE, empty); records++;
    PSS_PUT(stream, &off, MS, D3D12_SHADER_BYTECODE, empty); records++;
    D3D12_STREAM_OUTPUT_DESC so = { NULL, 0, NULL, 0, 5 };
    PSS_PUT(stream, &off, STREAM_OUTPUT, D3D12_STREAM_OUTPUT_DESC, so); records++;
    D3D12_BLEND_DESC blend; npt_test_fill(&blend, sizeof(blend), &seed);
    PSS_PUT(stream, &off, BLEND, D3D12_BLEND_DESC, blend); records++;
    UINT sample_mask = npt_test_rand(&seed);
    PSS_PUT(stream, &off, SAMPLE_MASK, UINT, sample_mask); records++;
    D3D12_RASTERIZER_DESC rast; npt_test_fill(&rast, sizeof(rast), &seed);
    PSS_PUT(stream, &off, RASTERIZER, D3D12_RASTERIZER_DESC, rast); records++;
    D3D12_DEPTH_STENCIL_DESC ds; npt_test_fill(&ds, sizeof(ds), &seed);
    PSS_PUT(stream, &off, DEPTH_STENCIL, D3D12_DEPTH_STENCIL_DESC, ds); records++;
    D3D12_INPUT_LAYOUT_DESC il = { NULL, 0 };
    PSS_PUT(stream, &off, INPUT_LAYOUT, D3D12_INPUT_LAYOUT_DESC, il); records++;
    D3D12_INDEX_BUFFER_STRIP_CUT_VALUE cut = D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFF;
    PSS_PUT(stream, &off, IB_STRIP_CUT_VALUE, D3D12_INDEX_BUFFER_STRIP_CUT_VALUE, cut); records++;
    D3D12_PRIMITIVE_TOPOLOGY_TYPE topo = D3D12_PRIMITIVE_TOPOLOGY_TYPE_LINE;
    PSS_PUT(stream, &off, PRIMITIVE_TOPOLOGY, D3D12_PRIMITIVE_TOPOLOGY_TYPE, topo); records++;
    D3D12_RT_FORMAT_ARRAY rts; npt_test_fill(&rts, sizeof(rts), &seed);
    PSS_PUT(stream, &off, RENDER_TARGET_FORMATS, D3D12_RT_FORMAT_ARRAY, rts); records++;
    DXGI_FORMAT dsv = DXGI_FORMAT_D24_UNORM_S8_UINT;
    PSS_PUT(stream, &off, DEPTH_STENCIL_FORMAT, DXGI_FORMAT, dsv); records++;
    DXGI_SAMPLE_DESC sd = { 1, 0 };
    PSS_PUT(stream, &off, SAMPLE_DESC, DXGI_SAMPLE_DESC, sd); records++;
    UINT node_mask = 0;
    PSS_PUT(stream, &off, NODE_MASK, UINT, node_mask); records++;
    D3D12_CACHED_PIPELINE_STATE cached = { NULL, 0 };
    PSS_PUT(stream, &off, CACHED_PSO, D3D12_CACHED_PIPELINE_STATE, cached); records++;
    D3D12_PIPELINE_STATE_FLAGS flags = D3D12_PIPELINE_STATE_FLAG_TOOL_DEBUG;
    PSS_PUT(stream, &off, FLAGS, D3D12_PIPELINE_STATE_FLAGS, flags); records++;
    D3D12_DEPTH_STENCIL_DESC1 ds1; npt_test_fill(&ds1, sizeof(ds1), &seed);
    PSS_PUT(stream, &off, DEPTH_STENCIL1, D3D12_DEPTH_STENCIL_DESC1, ds1); records++;
    D3D12_VIEW_INSTANCING_DESC vi = { 0, NULL, D3D12_VIEW_INSTANCING_FLAG_NONE };
    PSS_PUT(stream, &off, VIEW_INSTANCING, D3D12_VIEW_INSTANCING_DESC, vi); records++;
    D3D12_DEPTH_STENCIL_DESC2 ds2; npt_test_fill(&ds2, sizeof(ds2), &seed);
    PSS_PUT(stream, &off, DEPTH_STENCIL2, D3D12_DEPTH_STENCIL_DESC2, ds2); records++;
    D3D12_RASTERIZER_DESC1 rast1; npt_test_fill(&rast1, sizeof(rast1), &seed);
    PSS_PUT(stream, &off, RASTERIZER1, D3D12_RASTERIZER_DESC1, rast1); records++;
    D3D12_RASTERIZER_DESC2 rast2; npt_test_fill(&rast2, sizeof(rast2), &seed);
    PSS_PUT(stream, &off, RASTERIZER2, D3D12_RASTERIZER_DESC2, rast2); records++;

    D3D12_PIPELINE_STATE_STREAM_DESC orig = { off, stream };
    return pss_roundtrip("D3D12_PIPELINE_STATE_STREAM_DESC (all records)", &orig, records);
}

/* The runtime's parser accepts a stream whose last record omits its tail
 * padding (it loops while the offset is below SizeInBytes); so does this
 * codec, and the decoder rebuilds the record padded. */
static int test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_unpadded_tail(void)
{
    _Alignas(void *) uint8_t stream[512];
    memset(stream, 0, sizeof(stream));
    size_t off = 0;
    UINT node_mask = 3;
    PSS_PUT(stream, &off, NODE_MASK, UINT, node_mask);
    D3D12_BLEND_DESC blend; memset(&blend, 0, sizeof(blend));
    blend.RenderTarget[0].RenderTargetWriteMask = 0xF;
    size_t blend_at = off;
    PSS_PUT(stream, &off, BLEND, D3D12_BLEND_DESC, blend);
    /* sizeof(type) + sizeof(D3D12_BLEND_DESC) = 332 is not pointer-aligned:
     * cut SizeInBytes at the payload's end instead of the padded record. */
    size_t align, psize = npt_pss_payload(D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_BLEND, &align);
    size_t payload_off = (blend_at + sizeof(uint32_t) + align - 1) & ~(align - 1);
    size_t unpadded = payload_off + psize;
    if (unpadded == off) {
        fprintf(stderr, "FAIL: PIPELINE_STATE_STREAM (unpadded tail): case does not exercise padding\n");
        return -1;
    }
    D3D12_PIPELINE_STATE_STREAM_DESC orig = { unpadded, stream };

    size_t w_size = npt_sizeof_D3D12_PIPELINE_STATE_STREAM_DESC(&orig, 0);
    uint8_t *w = (uint8_t *)calloc(1, w_size ? w_size : 1);
    struct npt_cs_encoder enc = npt_test_encoder_init(w, w_size);
    npt_encode_D3D12_PIPELINE_STATE_STREAM_DESC(&enc, &orig);
    size_t w_actual = npt_test_encoder_written(&enc, w);

    D3D12_PIPELINE_STATE_STREAM_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w, w_actual);
    npt_decode_D3D12_PIPELINE_STATE_STREAM_DESC(&dec, &decoded);
    int result = 0;
    if (w_actual != w_size || decoded.SizeInBytes != off ||
        !decoded.pPipelineStateSubobjectStream ||
        memcmp(decoded.pPipelineStateSubobjectStream, stream, unpadded) != 0) {
        fprintf(stderr, "FAIL: PIPELINE_STATE_STREAM (unpadded tail): wrote %zu/%zu, size=%zu want %zu\n",
                w_actual, w_size, (size_t)decoded.SizeInBytes, off);
        result = -1;
    }
    npt_test_cleanup(&dec);
    free(w);
    return result;
}

/* Malformed streams -- an unknown record type, a record cut by
 * SizeInBytes, a base that is not pointer-aligned -- are unsized and
 * encode nothing, as the runtime rejects them with E_INVALIDARG.  A
 * NULL stream is the empty stream, whatever SizeInBytes says. */
static int test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_malformed(void)
{
    _Alignas(void *) uint8_t stream[256];
    memset(stream, 0, sizeof(stream));
    size_t off = 0;
    UINT node_mask = 3;
    PSS_PUT(stream, &off, NODE_MASK, UINT, node_mask);
    size_t good = off;
    uint32_t bogus = 0x7777;
    pss_put(stream, &off, D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_MAX_VALID, &bogus, sizeof(bogus), _Alignof(uint32_t));

    struct { const char *what; D3D12_PIPELINE_STATE_STREAM_DESC desc; int want_size; } cases[] = {
        { "unknown record type", { off, stream }, 0 },
        { "record cut by SizeInBytes", { good - 2, stream }, 0 },
        { "base not pointer-aligned", { good, stream + 2 }, 0 },
        { "NULL stream with nonzero size", { good, NULL }, 1 },
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        size_t w_size = npt_sizeof_D3D12_PIPELINE_STATE_STREAM_DESC(&cases[i].desc, 0);
        uint8_t w[64];
        memset(w, 0xEE, sizeof(w));
        struct npt_cs_encoder enc = npt_test_encoder_init(w, sizeof(w));
        npt_encode_D3D12_PIPELINE_STATE_STREAM_DESC(&enc, &cases[i].desc);
        size_t w_actual = npt_test_encoder_written(&enc, w);
        uint64_t count = 0xFFFF;
        if (w_actual >= sizeof(count))
            memcpy(&count, w, sizeof(count));
        if (cases[i].want_size) {
            /* the empty stream: an array count of zero, nothing else */
            if (w_size != sizeof(uint64_t) || w_actual != w_size || count != 0) {
                fprintf(stderr, "FAIL: PIPELINE_STATE_STREAM (%s): sizeof %zu wrote %zu count %llu\n",
                        cases[i].what, w_size, w_actual, (unsigned long long)count);
                return -1;
            }
        } else if (w_size != 0 || w_actual != 0) {
            fprintf(stderr, "FAIL: PIPELINE_STATE_STREAM (%s): sizeof %zu, wrote %zu; want nothing\n",
                    cases[i].what, w_size, w_actual);
            return -1;
        }
    }

    /* A wire record of unknown type stops the decoder with no stream. */
    {
        uint8_t w[16];
        uint64_t count = 1;
        int32_t type = D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_MAX_VALID;
        memcpy(w, &count, sizeof(count));
        memcpy(w + 8, &type, sizeof(type));
        D3D12_PIPELINE_STATE_STREAM_DESC decoded = { 99, stream };
        struct npt_cs_decoder dec = npt_test_decoder_init(w, sizeof(w));
        npt_decode_D3D12_PIPELINE_STATE_STREAM_DESC(&dec, &decoded);
        int result = 0;
        if (decoded.SizeInBytes != 0 || decoded.pPipelineStateSubobjectStream != NULL) {
            fprintf(stderr, "FAIL: PIPELINE_STATE_STREAM (unknown wire record): decoder kept a stream\n");
            result = -1;
        }
        npt_test_cleanup(&dec);
        return result;
    }
}

/* ------------------------------------------------------------------ */
/* Counted pointer presence with zero logical length                  */
/* ------------------------------------------------------------------ */

static int test_manual_counted_pointer_present_zero(void)
{
    D3D12_ROOT_SIGNATURE_DESC orig;
    memset(&orig, 0, sizeof(orig));

    D3D12_ROOT_PARAMETER dummy;
    memset(&dummy, 0, sizeof(dummy));

    orig.NumParameters = 0;
    orig.pParameters = &dummy;      /* present + logical count 0 */
    orig.NumStaticSamplers = 0;
    orig.pStaticSamplers = NULL;    /* absent + logical count 0 */

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC(&orig, 0);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC(&dec, &decoded);

    int result = 0;

    if (!decoded.pParameters || decoded.NumParameters != 0) {
        fprintf(stderr,
                "FAIL: present zero-length counted pointer lost presence "
                "(pParameters=%p NumParameters=%u)\n",
                (void *)decoded.pParameters, decoded.NumParameters);
        result = -1;
    }

    if (decoded.pStaticSamplers != NULL ||
        decoded.NumStaticSamplers != 0) {
        fprintf(stderr,
                "FAIL: absent zero-length counted pointer became present\n");
        result = -1;
    }

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC(&decoded, 0);
    uint8_t *w2 = (uint8_t *)calloc(1, w2_size ? w2_size : 1);
    struct npt_cs_encoder enc2 = npt_test_encoder_init(w2, w2_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC(&enc2, &decoded);
    size_t w2_actual = npt_test_encoder_written(&enc2, w2);

    if (npt_wire_compare("counted pointer present + zero length",
                         w1, w1_actual, w2, w2_actual))
        result = -1;

    npt_test_cleanup(&dec);
    free(w1);
    free(w2);
    return result;
}

static const struct manual_test_entry manual_tests[] = {
    { "D3D12_PIPELINE_STATE_STREAM_DESC (mesh pipeline records)",
      test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_mesh },
    { "D3D12_PIPELINE_STATE_STREAM_DESC (every record type)",
      test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_all_records },
    { "D3D12_PIPELINE_STATE_STREAM_DESC (unpadded last record)",
      test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_unpadded_tail },
    { "D3D12_PIPELINE_STATE_STREAM_DESC (malformed streams)",
      test_manual_D3D12_PIPELINE_STATE_STREAM_DESC_malformed },
    { "D3D11_AUTHENTICATED_PROTECTION_FLAGS (Value variant)",
      test_manual_D3D11_AUTHENTICATED_PROTECTION_FLAGS_Value },
    { "D3D11_AUTHENTICATED_PROTECTION_FLAGS (Flags variant)",
      test_manual_D3D11_AUTHENTICATED_PROTECTION_FLAGS_Flags },
    { "D3D12_RESOURCE_BARRIER (Transition variant)",
      test_manual_D3D12_RESOURCE_BARRIER_Transition },
    { "D3D12_RESOURCE_BARRIER (Aliasing variant)",
      test_manual_D3D12_RESOURCE_BARRIER_Aliasing },
    { "D3D12_RESOURCE_BARRIER (UAV variant)",
      test_manual_D3D12_RESOURCE_BARRIER_UAV },
    { "D3D12_ROOT_PARAMETER (Constants variant)",
      test_manual_D3D12_ROOT_PARAMETER_Constants },
    { "D3D12_ROOT_PARAMETER (DescriptorTable variant)",
      test_manual_D3D12_ROOT_PARAMETER_DescriptorTable },
    { "D3D12_ROOT_PARAMETER1 (Constants variant)",
      test_manual_D3D12_ROOT_PARAMETER1_Constants },
    { "D3D12_ROOT_SIGNATURE_DESC",
      test_manual_D3D12_ROOT_SIGNATURE_DESC },
    { "counted pointer present + zero length",
      test_manual_counted_pointer_present_zero },
    { "D3D12_ROOT_SIGNATURE_DESC1",
      test_manual_D3D12_ROOT_SIGNATURE_DESC1 },
    { "D3D12_ROOT_SIGNATURE_DESC2",
      test_manual_D3D12_ROOT_SIGNATURE_DESC2 },
    { "D3D12_VERSIONED_ROOT_SIGNATURE_DESC (v1.0)",
      test_manual_D3D12_VERSIONED_ROOT_SIGNATURE_DESC_1_0 },
    { "D3D12_BARRIER_GROUP (Global variant)",
      test_manual_D3D12_BARRIER_GROUP_Global },
    { "D3D12_BARRIER_GROUP (Texture variant)",
      test_manual_D3D12_BARRIER_GROUP_Texture },
    { "D3D12_BARRIER_GROUP (Buffer variant)",
      test_manual_D3D12_BARRIER_GROUP_Buffer },
    { "D3D12_RENDER_PASS_ENDING_ACCESS (Preserve variant)",
      test_manual_D3D12_RENDER_PASS_ENDING_ACCESS_Preserve },
    { "D3D12_RENDER_PASS_ENDING_ACCESS (Resolve variant)",
      test_manual_D3D12_RENDER_PASS_ENDING_ACCESS_Resolve },
    { "D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA",
      test_manual_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA },
    { "dispatch ID3D11DeviceContext::OMGetBlendState",
      test_manual_dispatch_OMGetBlendState },
    { "dispatch ID3D11VideoContext::GetDecoderBuffer",
      test_manual_dispatch_GetDecoderBuffer },
    { "dispatch ID3D12Resource::Map",
      test_manual_dispatch_Map },
    { "dispatch ID3D12VersionedRootSignatureDeserializer::GetRootSignatureDescAtVersion",
      test_manual_dispatch_GetRootSignatureDescAtVersion },
    { "dispatch D3D12CreateRootSignatureDeserializer",
      test_manual_dispatch_D3D12CreateRootSignatureDeserializer },
    { "dispatch D3D12CreateVersionedRootSignatureDeserializer",
      test_manual_dispatch_D3D12CreateVersionedRootSignatureDeserializer },
    { "reply unsupported DRED encode writes nothing",
      test_manual_reply_unsupported_encode_DRED },
};

#define MANUAL_TEST_COUNT \
    (int)(sizeof(manual_tests) / sizeof(manual_tests[0]))

/* Guest-side manual tests live in test_roundtrip_manual_guest.c because the
 * host and guest protocol headers define same-named static inline functions
 * and cannot share a translation unit (see tests/meson.build).  We chain
 * them in here so the runner sees a single contiguous list. */
extern int npt_guest_manual_test_count(void);
extern int npt_guest_manual_test_run(int index);
extern const char *npt_guest_manual_test_name(int index);

int manual_test_count(void)
{
    return MANUAL_TEST_COUNT + npt_guest_manual_test_count();
}

int run_manual_test(int index)
{
    if (index < 0)
        return -1;
    if (index < MANUAL_TEST_COUNT)
        return manual_tests[index].func();
    return npt_guest_manual_test_run(index - MANUAL_TEST_COUNT);
}

const char *manual_test_name(int index)
{
    if (index < 0)
        return "(invalid)";
    if (index < MANUAL_TEST_COUNT)
        return manual_tests[index].name;
    return npt_guest_manual_test_name(index - MANUAL_TEST_COUNT);
}

#pragma GCC diagnostic pop
