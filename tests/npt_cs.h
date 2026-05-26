/*
 * Copyright 2026 Turing Software LLC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Test stub implementation of the Neptune command stream interface.
 *
 * This file provides the types and functions that the generated protocol
 * headers expect from the consuming project's "npt_cs.h".  For compile
 * testing only -- all functions are stubs.
 */

#ifndef NPT_CS_H
#define NPT_CS_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <inttypes.h>
#include <wchar.h>

/* ------------------------------------------------------------------ */
/* Compiler helpers                                                    */
/* ------------------------------------------------------------------ */

#ifndef unlikely
# if defined(__GNUC__) || defined(__clang__)
#  define unlikely(x) __builtin_expect(!!(x), 0)
# else
#  define unlikely(x) (x)
# endif
#endif
#ifndef likely
# if defined(__GNUC__) || defined(__clang__)
#  define likely(x) __builtin_expect(!!(x), 1)
# else
#  define likely(x) (x)
# endif
#endif

/* ------------------------------------------------------------------ */
/* D3D/Windows type compatibility                                      */
/* ------------------------------------------------------------------ */

/*
 * On non-Windows, type definitions (HRESULT, GUID, RECT, POINT, enums,
 * structs, etc.) are provided by the generated npt_protocol_directx_types.h
 * header, which must be included before any protocol headers.
 *
 * On Windows, the real SDK types are used instead.
 */
#ifdef _WIN32
#include <windows.h>
#include <guiddef.h>
#endif

/* HRESULT values */
#define NPT_S_OK          ((HRESULT)0)
#define NPT_S_FALSE       ((HRESULT)1)
#define NPT_E_NOTIMPL     ((HRESULT)0x80004001)
#define NPT_E_NOINTERFACE ((HRESULT)0x80004002)
#define NPT_E_FAIL        ((HRESULT)0x80004005)
#define NPT_E_INVALIDARG  ((HRESULT)0x80070057)
#define NPT_E_OUTOFMEMORY ((HRESULT)0x8007000E)

#define NPT_SUCCEEDED(hr) ((HRESULT)(hr) >= 0)
#define NPT_FAILED(hr)    ((HRESULT)(hr) < 0)

/* ------------------------------------------------------------------ */
/* Object/handle types                                                 */
/* ------------------------------------------------------------------ */

typedef uint64_t npt_object_id;
typedef int npt_object_type;
#define NPT_OBJECT_TYPE_UNKNOWN ((npt_object_type)0)

/* ------------------------------------------------------------------ */
/* COM vtable access                                                   */
/* ------------------------------------------------------------------ */

static inline void **
npt_com_vtable(void *obj)
{
   return *(void ***)obj;
}

#define NPT_IUNKNOWN_VTBL_QUERY_INTERFACE 0
#define NPT_IUNKNOWN_VTBL_ADDREF          1
#define NPT_IUNKNOWN_VTBL_RELEASE         2

#define NPT_COM_VTBL_FUNC(type, vtable, idx)   \
   (((union { void *p; type f; }){ .p = (vtable)[(idx)] }).f)

/* ------------------------------------------------------------------ */
/* Logging                                                             */
/* ------------------------------------------------------------------ */

#define npt_log(...) ((void)0)

/* ------------------------------------------------------------------ */
/* Encoder                                                             */
/* ------------------------------------------------------------------ */

struct npt_cs_encoder {
   uint8_t *cur;
   const uint8_t *end;
};

static inline void
npt_cs_encoder_write(struct npt_cs_encoder *enc,
                     size_t size,
                     const void *val,
                     size_t val_size)
{
   assert(val_size <= size);
   if (unlikely(size > (size_t)(enc->end - enc->cur)))
      return;
   if (enc->cur != val)
      memcpy(enc->cur, val, val_size);
   enc->cur += size;
}

static inline void
npt_cs_encoder_set_fatal(const struct npt_cs_encoder *enc)
{
   (void)enc;
}

static inline bool
npt_cs_encoder_acquire(struct npt_cs_encoder *enc)
{
   (void)enc;
   return true;
}

static inline void
npt_cs_encoder_release(struct npt_cs_encoder *enc)
{
   (void)enc;
}

/* ------------------------------------------------------------------ */
/* Decoder                                                             */
/* ------------------------------------------------------------------ */

struct npt_cs_temp_alloc {
   struct npt_cs_temp_alloc *next;
   /* data follows */
};

struct npt_cs_decoder {
   const uint8_t *cur;
   const uint8_t *end;
   struct npt_cs_temp_alloc *temp_head;
};

static inline void
npt_cs_decoder_read(struct npt_cs_decoder *dec,
                    size_t size,
                    void *val,
                    size_t val_size)
{
   assert(val_size <= size);
   if (unlikely(size > (size_t)(dec->end - dec->cur))) {
      memset(val, 0, val_size);
      return;
   }
   if (dec->cur != val)
      memcpy(val, dec->cur, val_size);
   dec->cur += size;
}

static inline void
npt_cs_decoder_peek(const struct npt_cs_decoder *dec,
                    size_t size,
                    void *val,
                    size_t val_size)
{
   assert(val_size <= size);
   if (unlikely(size > (size_t)(dec->end - dec->cur))) {
      memset(val, 0, val_size);
      return;
   }
   if (dec->cur != val)
      memcpy(val, dec->cur, val_size);
}

static inline void
npt_cs_decoder_set_fatal(const struct npt_cs_decoder *dec)
{
   (void)dec;
}

static inline bool
npt_cs_decoder_get_fatal(const struct npt_cs_decoder *dec)
{
   (void)dec;
   return false;
}

static inline void *
npt_cs_decoder_alloc_temp(struct npt_cs_decoder *dec, size_t size)
{
   struct npt_cs_temp_alloc *node = (struct npt_cs_temp_alloc *)
       malloc(sizeof(struct npt_cs_temp_alloc) + size);
   if (!node) return NULL;
   node->next = dec->temp_head;
   dec->temp_head = node;
   void *ptr = (void *)(node + 1);
   memset(ptr, 0, size);
   return ptr;
}

static inline void *
npt_cs_decoder_alloc_temp_array(struct npt_cs_decoder *dec,
                                size_t element_size,
                                size_t count)
{
   if (count && element_size > SIZE_MAX / count)
      return NULL;
   return npt_cs_decoder_alloc_temp(dec, element_size * count);
}

static inline void
npt_cs_decoder_reset_temp_pool(struct npt_cs_decoder *dec)
{
   struct npt_cs_temp_alloc *node = dec->temp_head;
   while (node) {
      struct npt_cs_temp_alloc *next = node->next;
      free(node);
      node = next;
   }
   dec->temp_head = NULL;
}

/* ------------------------------------------------------------------ */
/* Ring submission (guest-side)                                        */
/* ------------------------------------------------------------------ */

struct npt_ring;
struct npt_ring_submit_command {
   void *cmd_data;
   size_t cmd_size;
   size_t reply_size;
   struct npt_cs_encoder enc;
   struct npt_cs_decoder dec;
};

static inline struct npt_cs_encoder *
npt_ring_submit_command_init(struct npt_ring *ring,
                             struct npt_ring_submit_command *submit,
                             void *cmd_data, size_t cmd_size,
                             size_t reply_size)
{
   (void)ring;
   submit->cmd_data = cmd_data;
   submit->cmd_size = cmd_size;
   submit->reply_size = reply_size;
   submit->enc.cur = (uint8_t *)cmd_data;
   submit->enc.end = (uint8_t *)cmd_data + cmd_size;
   return &submit->enc;
}

static inline void
npt_ring_submit_command(struct npt_ring *ring,
                        struct npt_ring_submit_command *submit)
{
   (void)ring; (void)submit;
}

static inline struct npt_cs_decoder *
npt_ring_get_command_reply(struct npt_ring *ring,
                           struct npt_ring_submit_command *submit)
{
   (void)ring;
   if (!submit->reply_size)
      return NULL;
   submit->dec.cur = NULL;
   submit->dec.end = NULL;
   return &submit->dec;
}

static inline void
npt_ring_free_command_reply(struct npt_ring *ring,
                            struct npt_ring_submit_command *submit)
{
   (void)ring; (void)submit;
}

/* ------------------------------------------------------------------ */
/* Object/handle management                                            */
/* ------------------------------------------------------------------ */

struct npt_dispatch_context;

static inline void *
npt_cs_handle_lookup(struct npt_dispatch_context *ctx,
                     npt_object_id id,
                     npt_object_type type)
{
   (void)ctx; (void)id; (void)type;
   return NULL;
}

static inline void
npt_cs_handle_register_guest_id(struct npt_dispatch_context *ctx,
                                npt_object_id guest_id,
                                void *obj,
                                npt_object_type type)
{
   (void)ctx; (void)guest_id; (void)obj; (void)type;
}

/* Test harness stub for the guest-side id allocator (the generated
 * encoders call it).  Monotonic counter is fine for test purposes; no
 * coordination with a real runtime. */
static inline uint64_t
npt_com_allocate_next_id(void)
{
   static uint64_t next = 1;
   return next++;
}

static inline void *
npt_win32_handle_replace(struct npt_dispatch_context *ctx,
                         npt_object_id id)
{
   (void)ctx; (void)id;
   return NULL;
}

/* Event HANDLEs (handle="event" in the overlay) use a distinct replace hook
 * that maps an unregistered id to NULL rather than the identity fallback. */
static inline void *
npt_event_handle_replace(struct npt_dispatch_context *ctx,
                         npt_object_id id)
{
   (void)ctx; (void)id;
   return NULL;
}

static inline npt_object_id
npt_object_get_id(const void *handle)
{
   return (npt_object_id)(uintptr_t)handle;
}

static inline void *
npt_object_from_id(npt_object_id id)
{
   return (void *)(uintptr_t)id;
}

static inline npt_object_id
npt_win32_handle_get_id(const void *handle)
{
   return (npt_object_id)(uintptr_t)handle;
}

static inline void *
npt_win32_handle_from_id(npt_object_id id)
{
   return (void *)(uintptr_t)id;
}

#endif /* NPT_CS_H */
