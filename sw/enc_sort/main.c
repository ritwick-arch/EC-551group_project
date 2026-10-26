#include "io.h"
#include "se.h"
#include "inputs.h"

static ct_t vec[NUM_INPUTS];
static uint32_t min_cycles, max_cycles;

// Runs one SE op and records how many cycles it took.
static void timed_op(int op, const ct_t *a, const ct_t *b, const ct_t *c, ct_t *r)
{
  uint32_t t = se_cycles();
  se_op(op, a, b, c, r);
  t = se_cycles() - t;
  if (t < min_cycles)
    min_cycles = t;
  if (t > max_cycles)
    max_cycles = t;
}

static void print_vec(const char *label)
{
  for (int i = 0; i < NUM_INPUTS; i++)
  {
    print_str(label);
    print_uint(i);
    print_str(i < 10 ? "  " : " ");
    print_ct(&vec[i]);
    print_str("\r\n");
  }
}

void main(void)
{
  ct_t gt, lo, hi;

  // RAM is not reinitialised on CPU reset, so set state explicitly.
  min_cycles = 0xFFFFFFFF;
  max_cycles = 0;
  for (int i = 0; i < NUM_INPUTS; i++)
    ct_copy(&vec[i], &inputs[i]);
  print_str("Encrypted sort: the CPU only sees ciphertext\r\n");
  print_vec("in  ");

  // Bubble sort without branching on secret data: always compare, then swap via CMOV.
  for (int i = 0; i < NUM_INPUTS - 1; i++)
    for (int j = 0; j < NUM_INPUTS - 1 - i; j++)
    {
      timed_op(SE_LT, &vec[j + 1], &vec[j], 0, &gt);
      timed_op(SE_CMOV, &vec[j + 1], &vec[j], &gt, &lo);
      timed_op(SE_CMOV, &vec[j], &vec[j + 1], &gt, &hi);
      ct_copy(&vec[j], &lo);
      ct_copy(&vec[j + 1], &hi);
    }

  print_vec("out ");
  print_str("SE op cycles: min ");
  print_uint(min_cycles);
  print_str(" max ");
  print_uint(max_cycles);
  print_str("\r\ndone\r\n");
}
