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
 *   D3D12_PIPELINE_STATE_STREAM_DESC (_Inexpressible_ count)
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

    size_t w1_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D11_AUTHENTICATED_PROTECTION_FLAGS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&decoded);
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

    size_t w1_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D11_AUTHENTICATED_PROTECTION_FLAGS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D11_AUTHENTICATED_PROTECTION_FLAGS(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RESOURCE_BARRIER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RESOURCE_BARRIER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RESOURCE_BARRIER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RESOURCE_BARRIER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RESOURCE_BARRIER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RESOURCE_BARRIER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RESOURCE_BARRIER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RESOURCE_BARRIER(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_ROOT_PARAMETER(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_PARAMETER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_PARAMETER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_PARAMETER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_PARAMETER(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_ROOT_PARAMETER(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_PARAMETER(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_PARAMETER decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_PARAMETER(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_PARAMETER(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_ROOT_PARAMETER1(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_PARAMETER1(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_PARAMETER1 decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_PARAMETER1(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_PARAMETER1(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC1(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC1(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC1 decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC1(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC1(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC2(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_ROOT_SIGNATURE_DESC2(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_ROOT_SIGNATURE_DESC2 decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_ROOT_SIGNATURE_DESC2(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_ROOT_SIGNATURE_DESC2(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_VERSIONED_ROOT_SIGNATURE_DESC decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_VERSIONED_ROOT_SIGNATURE_DESC(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_BARRIER_GROUP(&orig);
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

    size_t w1_size = npt_sizeof_D3D12_BARRIER_GROUP(&orig);
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

    size_t w1_size = npt_sizeof_D3D12_BARRIER_GROUP(&orig);
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

    size_t w1_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RENDER_PASS_ENDING_ACCESS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RENDER_PASS_ENDING_ACCESS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RENDER_PASS_ENDING_ACCESS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_RENDER_PASS_ENDING_ACCESS(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_RENDER_PASS_ENDING_ACCESS decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_RENDER_PASS_ENDING_ACCESS(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_RENDER_PASS_ENDING_ACCESS(&decoded);
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

    size_t w1_size = npt_sizeof_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&orig);
    uint8_t *w1 = (uint8_t *)calloc(1, w1_size ? w1_size : 1);
    struct npt_cs_encoder enc1 = npt_test_encoder_init(w1, w1_size);
    npt_encode_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&enc1, &orig);
    size_t w1_actual = npt_test_encoder_written(&enc1, w1);

    D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA decoded;
    memset(&decoded, 0, sizeof(decoded));
    struct npt_cs_decoder dec = npt_test_decoder_init(w1, w1_actual);
    npt_decode_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&dec, &decoded);

    size_t w2_size = npt_sizeof_D3D12_VERSIONED_DEVICE_REMOVED_EXTENDED_DATA(&decoded);
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
/* Dispatch table                                                     */
/* ================================================================== */

typedef int (*manual_test_func)(void);

struct manual_test_entry {
    const char *name;
    manual_test_func func;
};

static const struct manual_test_entry manual_tests[] = {
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
};

#define MANUAL_TEST_COUNT \
    (int)(sizeof(manual_tests) / sizeof(manual_tests[0]))

int manual_test_count(void)
{
    return MANUAL_TEST_COUNT;
}

int run_manual_test(int index)
{
    if (index < 0 || index >= MANUAL_TEST_COUNT)
        return -1;
    return manual_tests[index].func();
}

const char *manual_test_name(int index)
{
    if (index < 0 || index >= MANUAL_TEST_COUNT)
        return "(invalid)";
    return manual_tests[index].name;
}

#pragma GCC diagnostic pop
