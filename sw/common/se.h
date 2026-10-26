// Driver for the SE unit at 0x80040000; software only ever handles ciphertext.
#ifndef SE_H
#define SE_H

#include <stdint.h>

typedef struct
{
  uint32_t w[4];
} ct_t;

enum
{
  SE_ADD,
  SE_SUB,
  SE_MUL,
  SE_LT,
  SE_EQ,
  SE_CMOV
};

#define SE_BASE ((volatile uint32_t *)0x80040000)

static inline uint32_t se_cycles(void)
{
  uint32_t c;
  asm volatile("csrr %0, mcycle" : "=r"(c));
  return c;
}

static inline void ct_copy(ct_t *dst, const ct_t *src)
{
  for (int i = 0; i < 4; i++)
    dst->w[i] = src->w[i];
}

// r = op(a, b); for SE_CMOV, r = c ? a : b.
static inline void se_op(int op, const ct_t *a, const ct_t *b, const ct_t *c, ct_t *r)
{
  volatile uint32_t *se = SE_BASE;
  for (int i = 0; i < 4; i++)
  {
    se[i] = a->w[i];
    se[4 + i] = b->w[i];
    se[8 + i] = c ? c->w[i] : 0;
  }
  se[16] = op;
  while (se[17] & 1)
    ;
  for (int i = 0; i < 4; i++)
    r->w[i] = se[12 + i];
}

#endif
