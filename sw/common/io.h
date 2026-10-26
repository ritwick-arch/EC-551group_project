// UART printing helpers that avoid division, since programs link without libgcc.
#ifndef IO_H
#define IO_H

#include "libsteel.h"
#include "se.h"

#define UART ((UartController *)0x80000000)

static inline void print_str(const char *s)
{
  uart_write_string(UART, s);
}

static inline void print_uint(uint32_t u)
{
  static const uint32_t powers[] = {1000000000, 100000000, 10000000, 1000000,
                                    100000, 10000, 1000, 100, 10, 1};
  int started = 0;
  for (int i = 0; i < 10; i++)
  {
    char d = '0';
    while (u >= powers[i])
    {
      u -= powers[i];
      d++;
    }
    if (d != '0' || started || i == 9)
    {
      uart_write(UART, d);
      started = 1;
    }
  }
}

static inline void print_hex32(uint32_t v)
{
  for (int s = 28; s >= 0; s -= 4)
    uart_write(UART, "0123456789abcdef"[(v >> s) & 0xF]);
}

// Prints a ciphertext as 32 hex digits, most significant word first.
static inline void print_ct(const ct_t *c)
{
  for (int i = 3; i >= 0; i--)
    print_hex32(c->w[i]);
}

#endif
