#include "io.h"
#include "se.h"

#define MAX_N 16
#define RAM_SIZE 0x2000

// The elements sit at a fixed address (0x1800, see link.ld) so they can be watched in memory.
static ct_t vec[MAX_N] __attribute__((section(".vec")));
static char line[48];
static int n, se_mode, step_i, step_j;

static int starts_with(const char *s, const char *prefix)
{
  while (*prefix)
    if (*s++ != *prefix++)
      return 0;
  return 1;
}

// Reads memory through a non-inlined call so the compiler cannot special-case any address.
__attribute__((noinline)) static uint32_t read_word(uint32_t addr)
{
  return *(volatile uint32_t *)addr;
}

// Prints count words read straight from memory, per_line words to a line.
static void print_words(const char *tag, uint32_t addr, int count, int per_line)
{
  for (int i = 0; i < count; i += per_line)
  {
    print_str(tag);
    print_hex32(addr + 4 * i);
    for (int k = 0; k < per_line; k++)
    {
      uart_write(UART, ' ');
      print_hex32(read_word(addr + 4 * (i + k)));
    }
    print_str("\r\n");
  }
}

// One compare-and-swap in plaintext: anyone who can read memory sees the values.
__attribute__((noinline)) static void plain_step(int j)
{
  int32_t a = (int32_t)vec[j].w[0], b = (int32_t)vec[j + 1].w[0];
  if (b < a)
  {
    vec[j].w[0] = b;
    vec[j + 1].w[0] = a;
  }
}

// The same step through the SE unit: both slots get fresh ciphertext whether or not they swap.
__attribute__((noinline)) static void se_step(int j)
{
  ct_t gt, lo, hi;
  se_op(SE_LT, &vec[j + 1], &vec[j], &vec[j], &gt);
  se_op(SE_CMOV, &vec[j + 1], &vec[j], &gt, &lo);
  se_op(SE_CMOV, &vec[j], &vec[j + 1], &gt, &hi);
  ct_copy(&vec[j], &lo);
  ct_copy(&vec[j + 1], &hi);
}

// "load plain N" or "load se N", followed by N lines of decimal values or ciphertexts.
static void load(const char *args)
{
  se_mode = starts_with(args, "se ");
  if (!se_mode && !starts_with(args, "plain "))
  {
    print_str("bad mode\r\n");
    return;
  }
  n = parse_int(args + (se_mode ? 3 : 6));
  if (n < 0 || n > MAX_N)
    n = 0;
  volatile uint32_t *words = vec[0].w;
  for (int k = 0; k < 4 * MAX_N; k++)
    words[k] = 0;
  for (int i = 0; i < n; i++)
  {
    read_line(line, sizeof line);
    if (se_mode)
      parse_ct(line, &vec[i]);
    else
      vec[i].w[0] = parse_int(line);
  }
  step_i = step_j = 0;
}

// Runs the next bubble-sort compare-and-swap, then shows the slots as they are in memory.
static void step(void)
{
  if (step_i >= n - 1)
  {
    print_str("sorted\r\n");
    return;
  }
  int j = step_j;
  uint32_t t = se_cycles();
  if (se_mode)
    se_step(j);
  else
    plain_step(j);
  t = se_cycles() - t;
  if (++step_j >= n - 1 - step_i)
  {
    step_j = 0;
    step_i++;
  }
  print_str("step ");
  print_uint(j);
  print_str(" ");
  print_uint(t);
  print_str("\r\n");
  print_words("m ", (uint32_t)vec, 4 * n, 4);
}

void main(void)
{
  // RAM is not reinitialised on CPU reset, so set state explicitly.
  n = step_i = step_j = 0;
  print_str("SE sort demo\r\nready\r\n");

  // Commands from host/owner.py demo, one per line; each reply ends with "ok".
  for (;;)
  {
    read_line(line, sizeof line);
    if (line[0] == '\0')
    {
      print_str("ready\r\n");
      continue;
    }
    if (starts_with(line, "load "))
      load(line + 5);
    else if (starts_with(line, "step"))
      step();
    else if (starts_with(line, "show"))
      print_words("m ", (uint32_t)vec, 4 * n, 4);
    else if (starts_with(line, "dump"))
      print_words("d ", 0, RAM_SIZE / 4, 8);
    else if (starts_with(line, "peek "))
      print_words("p ", parse_hex(line + 5, 8) & ~3u, 1, 1);
    else
      print_str("?\r\n");
    print_str("ok\r\n");
  }
}
