// UART helpers that avoid division, since programs link without libgcc.
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

// Reads one line from the UART, dropping '\r', and returns its length.
static inline int read_line(char *buf, int size)
{
  int n = 0;
  for (;;)
  {
    while (!uart_data_received(UART))
      ;
    char ch = uart_read(UART);
    if (ch == '\n')
      break;
    if (ch != '\r' && n < size - 1)
      buf[n++] = ch;
  }
  buf[n] = '\0';
  return n;
}

static inline int hex_digit(char ch)
{
  if (ch >= '0' && ch <= '9')
    return ch - '0';
  if (ch >= 'a' && ch <= 'f')
    return ch - 'a' + 10;
  if (ch >= 'A' && ch <= 'F')
    return ch - 'A' + 10;
  return -1;
}

// Parses up to n hex digits, stopping at the first non-hex character.
static inline uint32_t parse_hex(const char *s, int n)
{
  uint32_t v = 0;
  for (int d; n > 0 && (d = hex_digit(*s)) >= 0; n--, s++)
    v = (v << 4) | d;
  return v;
}

// Parses 32 hex digits, most significant word first, as printed by print_ct.
static inline void parse_ct(const char *s, ct_t *c)
{
  for (int i = 0; i < 4; i++)
    c->w[3 - i] = parse_hex(s + 8 * i, 8);
}

// Parses a decimal number with an optional leading '-'.
static inline int32_t parse_int(const char *s)
{
  int neg = *s == '-';
  int32_t v = 0;
  for (s += neg; *s >= '0' && *s <= '9'; s++)
    v = v * 10 + (*s - '0');
  return neg ? -v : v;
}

#endif
