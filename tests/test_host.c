/*
 * Copyright 2026 Turing Software LLC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Compile test for host-side (decoder + dispatch) generated headers.
 * This file must compile without errors or warnings.
 */

#include "npt_protocol_host.h"

/*
 * Exercise the generated code so the compiler doesn't optimize it away.
 * We call representative functions from each category.
 */
volatile int npt_test_sink;

void test_dispatch(void)
{
    struct npt_dispatch_context ctx;
    memset(&ctx, 0, sizeof(ctx));
    /* Would crash at runtime but we only need compile + link */
    if (0)
        npt_dispatch_command(&ctx);
    npt_test_sink = sizeof(ctx);
}

void test_struct_encode(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));

    D3D12_COMMAND_QUEUE_DESC desc;
    memset(&desc, 0, sizeof(desc));
    if (0) {
        npt_encode_D3D12_COMMAND_QUEUE_DESC(&enc, &desc);
        npt_test_sink += (int)npt_sizeof_D3D12_COMMAND_QUEUE_DESC(&desc);
    }

    DXGI_SWAP_CHAIN_DESC sc_desc;
    memset(&sc_desc, 0, sizeof(sc_desc));
    if (0) {
        npt_encode_DXGI_SWAP_CHAIN_DESC(&enc, &sc_desc);
        npt_test_sink += (int)npt_sizeof_DXGI_SWAP_CHAIN_DESC(&sc_desc);
    }
}

void test_struct_decode(void)
{
    struct npt_cs_decoder dec;
    memset(&dec, 0, sizeof(dec));

    D3D12_COMMAND_QUEUE_DESC desc;
    if (0)
        npt_decode_D3D12_COMMAND_QUEUE_DESC(&dec, &desc);

    D3D12_GRAPHICS_PIPELINE_STATE_DESC pso;
    if (0)
        npt_decode_D3D12_GRAPHICS_PIPELINE_STATE_DESC(&dec, &pso);

    npt_test_sink += sizeof(desc) + sizeof(pso);
}

void test_command_decode(void)
{
    struct npt_cs_decoder dec;
    memset(&dec, 0, sizeof(dec));

    struct npt_command_ID3D12Device_CreateCommandQueue args;
    if (0)
        npt_decode_ID3D12Device_CreateCommandQueue_args_temp(&dec, &args);

    struct npt_command_D3D11CreateDevice d3d11_args;
    if (0)
        npt_decode_D3D11CreateDevice_args_temp(&dec, &d3d11_args);

    npt_test_sink += sizeof(args) + sizeof(d3d11_args);
}

void test_reply_encode(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));

    struct npt_command_ID3D12Device_CreateCommandQueue args;
    memset(&args, 0, sizeof(args));
    if (0)
        npt_encode_ID3D12Device_CreateCommandQueue_reply(&enc, &args);

    npt_test_sink += sizeof(args);
}

void test_replace_handle(void)
{
    struct npt_dispatch_context ctx;
    memset(&ctx, 0, sizeof(ctx));

    struct npt_command_ID3D12Device_CreateComputePipelineState args;
    memset(&args, 0, sizeof(args));
    if (0)
        npt_replace_ID3D12Device_CreateComputePipelineState_args_handle(&ctx, &args);

    npt_test_sink += sizeof(args);
}

void test_types(void)
{
    struct npt_cs_encoder enc;
    memset(&enc, 0, sizeof(enc));
    struct npt_cs_decoder dec;
    memset(&dec, 0, sizeof(dec));

    UINT u = 42;
    DXGI_FORMAT fmt = DXGI_FORMAT_UNKNOWN;
    if (0) {
        npt_encode_UINT(&enc, &u);
        npt_encode_DXGI_FORMAT(&enc, &fmt);
        npt_decode_UINT(&dec, &u);
        npt_decode_DXGI_FORMAT(&dec, &fmt);
        npt_test_sink += (int)npt_sizeof_UINT(&u);
        npt_test_sink += (int)npt_sizeof_DXGI_FORMAT(&fmt);
    }
}

int main(void)
{
    test_dispatch();
    test_struct_encode();
    test_struct_decode();
    test_command_decode();
    test_reply_encode();
    test_replace_handle();
    test_types();
    return npt_test_sink;
}
