/*
 * Copyright 2026 Turing Software LLC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Compile test for guest-side (encoder) generated headers.
 * This file must compile without errors or warnings.
 */

#include "npt_protocol_guest.h"

/*
 * Exercise the generated guest-side code.
 */
volatile int npt_test_sink;

void test_command_encode(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));

    D3D12_COMMAND_QUEUE_DESC desc;
    memset(&desc, 0, sizeof(desc));
    IID riid;
    memset(&riid, 0, sizeof(riid));
    void *out = NULL;

    if (0) {
        npt_encode_ID3D12Device_CreateCommandQueue(
            &enc, NPT_CMD_FLAG_REPLY, 1, &desc, &riid, &out);
        npt_test_sink += (int)npt_sizeof_ID3D12Device_CreateCommandQueue(
            &desc, &riid, &out);
        npt_test_sink += (int)npt_sizeof_ID3D12Device_CreateCommandQueue_reply(
            &desc, &riid, &out);
    }
}

void test_command_encode_toplevel(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));

    if (0)
        npt_encode_DXGIDeclareAdapterRemovalSupport(&enc, 0);

    npt_test_sink += sizeof(struct npt_command_DXGIDeclareAdapterRemovalSupport);
}

void test_submit_call(void)
{
    struct npt_ring *ring = NULL;

    D3D12_COMMAND_QUEUE_DESC desc;
    memset(&desc, 0, sizeof(desc));
    IID riid;
    memset(&riid, 0, sizeof(riid));
    void *out = NULL;

    if (0) {
        npt_async_ID3D12Device_CreateCommandQueue(
            ring, 1, &desc, &riid, &out);
        HRESULT hr = npt_call_ID3D12Device_CreateCommandQueue(
            ring, 1, &desc, &riid, &out);
        npt_test_sink += hr;
    }
}

void test_reply_decode(void)
{
    struct npt_cs_decoder dec;
    memset(&dec, 0, sizeof(dec));

    void *out = NULL;
    HRESULT ret;
    if (0)
        npt_decode_ID3D12Device_CreateCommandQueue_reply(&dec, &out, &ret);

    /* Return-value-only reply */
    UINT node_count = 0;
    if (0)
        npt_decode_ID3D12Device_GetNodeCount_reply(&dec, &node_count);
    npt_test_sink += (int)(uintptr_t)out + (int)node_count;
}

void test_struct_encode(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));

    D3D12_GRAPHICS_PIPELINE_STATE_DESC pso;
    memset(&pso, 0, sizeof(pso));
    if (0) {
        npt_encode_D3D12_GRAPHICS_PIPELINE_STATE_DESC(&enc, &pso);
        npt_test_sink += (int)npt_sizeof_D3D12_GRAPHICS_PIPELINE_STATE_DESC(&pso);
    }

    DXGI_PRESENT_PARAMETERS pp;
    memset(&pp, 0, sizeof(pp));
    if (0) {
        npt_encode_DXGI_PRESENT_PARAMETERS(&enc, &pp);
        npt_test_sink += (int)npt_sizeof_DXGI_PRESENT_PARAMETERS(&pp);
    }
}

void test_types(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));
    struct npt_cs_decoder dec;
    memset(&dec, 0, sizeof(dec));

    UINT u = 42;
    D3D12_COMMAND_LIST_TYPE type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    if (0) {
        npt_encode_UINT(&enc, &u);
        npt_encode_D3D12_COMMAND_LIST_TYPE(&enc, &type);
        npt_decode_UINT(&dec, &u);
        npt_decode_D3D12_COMMAND_LIST_TYPE(&dec, &type);
        npt_test_sink += (int)npt_sizeof_UINT(&u);
        npt_test_sink += (int)npt_sizeof_D3D12_COMMAND_LIST_TYPE(&type);
    }
}

int main(void)
{
    test_command_encode();
    test_command_encode_toplevel();
    test_submit_call();
    test_reply_decode();
    test_struct_encode();
    test_types();
    return npt_test_sink;
}
