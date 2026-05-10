/*
 * Copyright 2026 Turing Software LLC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Test harness for Neptune protocol roundtrip tests.
 * Provides deterministic PRNG, wire comparison, allocation tracking,
 * and handle tracking utilities.
 */

#ifndef NPT_TEST_HARNESS_H
#define NPT_TEST_HARNESS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <limits.h>

/* ------------------------------------------------------------------ */
/* Deterministic PRNG (xorshift32)                                     */
/* ------------------------------------------------------------------ */

static inline uint32_t
npt_test_rand(uint32_t *state)
{
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static inline void
npt_test_fill(void *buf, size_t size, uint32_t *seed)
{
    /* Fill 32-bit at a time with values capped to 8 bits (0-255) to keep
     * count-like struct fields small.  Count fields used for array sizes
     * are overridden to explicit values (0/1/5) by the init functions, so
     * this cap only affects non-count scalar fields.  Using 0xFF instead
     * of the full 32-bit range prevents accidental huge values when a
     * random-filled struct is used as input to a method with an expression
     * like count = pDesc->MipLevels * pDesc->ArraySize. */
    uint32_t *p32 = (uint32_t *)buf;
    size_t n32 = size / 4;
    for (size_t i = 0; i < n32; i++)
        p32[i] = npt_test_rand(seed) & 0xFF;
    uint8_t *tail = (uint8_t *)(p32 + n32);
    for (size_t i = 0; i < size % 4; i++)
        tail[i] = (uint8_t)npt_test_rand(seed);
}

static inline uint64_t
npt_test_u64(uint32_t *seed)
{
    uint64_t hi = npt_test_rand(seed);
    uint64_t lo = npt_test_rand(seed);
    return (hi << 32) | lo;
}

/* ------------------------------------------------------------------ */
/* Wire buffer comparison                                              */
/* ------------------------------------------------------------------ */

static inline int
npt_wire_compare(const char *test_name,
                 const uint8_t *w1, size_t s1,
                 const uint8_t *w2, size_t s2)
{
    if (s1 != s2) {
        fprintf(stderr, "FAIL: %s: wire size mismatch: %zu vs %zu\n",
                test_name, s1, s2);
        return -1;
    }
    for (size_t i = 0; i < s1; i++) {
        if (w1[i] != w2[i]) {
            fprintf(stderr, "FAIL: %s: wire mismatch at offset %zu: "
                    "0x%02x vs 0x%02x\n", test_name, i, w1[i], w2[i]);
            return -1;
        }
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* Encoder/decoder helpers                                             */
/* ------------------------------------------------------------------ */

static inline struct npt_cs_encoder
npt_test_encoder_init(uint8_t *buf, size_t size)
{
    struct npt_cs_encoder enc;
    enc.cur = buf;
    enc.end = buf + size;
    return enc;
}

static inline size_t
npt_test_encoder_written(const struct npt_cs_encoder *enc, const uint8_t *buf)
{
    return (size_t)(enc->cur - buf);
}

static inline struct npt_cs_decoder
npt_test_decoder_init(const uint8_t *buf, size_t size)
{
    struct npt_cs_decoder dec;
    dec.cur = buf;
    dec.end = buf + size;
    dec.temp_head = NULL;
    return dec;
}

/* ------------------------------------------------------------------ */
/* Tracked allocation pool (for test data, freed in bulk)              */
/* ------------------------------------------------------------------ */

#define NPT_TEST_MAX_ALLOCS 4096

static void *npt_test_alloc_pool[NPT_TEST_MAX_ALLOCS];
static int npt_test_alloc_count = 0;

/* Maximum total allocation for test arrays (prevent OOM from random counts) */
#define NPT_TEST_MAX_ALLOC_BYTES 4096

/* Clamp a count value to prevent huge allocations from random data.
 * The clamp is based on total bytes (count * elem_size). */
static inline size_t
npt_test_clamp_count(size_t count, size_t elem_size)
{
    if (elem_size == 0) elem_size = 1;
    size_t max_count = NPT_TEST_MAX_ALLOC_BYTES / elem_size;
    if (max_count == 0) max_count = 1;
    return count > max_count ? max_count : count;
}

static inline void *
npt_test_alloc(size_t size)
{
    void *p = calloc(1, size > 0 ? size : 1);
    if (p && npt_test_alloc_count < NPT_TEST_MAX_ALLOCS)
        npt_test_alloc_pool[npt_test_alloc_count++] = p;
    return p;
}

static inline void
npt_test_alloc_free_all(void)
{
    for (int i = 0; i < npt_test_alloc_count; i++)
        free(npt_test_alloc_pool[i]);
    npt_test_alloc_count = 0;
}

/* ------------------------------------------------------------------ */
/* Handle creation (for struct tests with COM/Win32 handle fields)     */
/* ------------------------------------------------------------------ */

static inline void *
npt_test_handle_create(uint32_t *seed)
{
    /* Generate a non-zero, alignment-safe fake pointer value */
    uint64_t id = (npt_test_u64(seed) | 0x1000ULL) & ~(uint64_t)0x7;
    return (void *)(uintptr_t)id;
}

/* ------------------------------------------------------------------ */
/* String creation                                                     */
/* ------------------------------------------------------------------ */

static inline char *
npt_test_string(uint32_t *seed, size_t len)
{
    char *s = (char *)npt_test_alloc(len + 1);
    for (size_t i = 0; i < len; i++)
        s[i] = 'a' + (char)(npt_test_rand(seed) % 26);
    s[len] = '\0';
    return s;
}

/* WCHAR is uint16_t (not wchar_t which is 4 bytes on Linux).
 * The npt_cs.h header must be included before this header so WCHAR
 * is defined via npt_protocol_directx_types.h. */
static inline WCHAR *
npt_test_wstring(uint32_t *seed, size_t len)
{
    WCHAR *s = (WCHAR *)npt_test_alloc((len + 1) * sizeof(WCHAR));
    for (size_t i = 0; i < len; i++)
        s[i] = (WCHAR)('A' + (npt_test_rand(seed) % 26));
    s[len] = 0;
    return s;
}

/* ------------------------------------------------------------------ */
/* Test cleanup (call after each test)                                 */
/* ------------------------------------------------------------------ */

static inline void
npt_test_cleanup(struct npt_cs_decoder *dec)
{
    if (dec)
        npt_cs_decoder_reset_temp_pool(dec);
    npt_test_alloc_free_all();
}

#endif /* NPT_TEST_HARNESS_H */
