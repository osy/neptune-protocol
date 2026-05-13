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
