#include "libsteel.h"

#define UART (UartController *)0x80000000
#define N 16

static int vec[N] = {29, -3, 17, 8, 0, 42, -15, 11, 5, 23, -7, 36, 2, 14, -1, 9};

// Prints a signed integer in decimal using subtraction, since RV32I has no divide.
static void print_int(int x)
{
  static const unsigned powers[] = {1000000000, 100000000, 10000000, 1000000,
                                    100000, 10000, 1000, 100, 10, 1};
  unsigned u = x < 0 ? -(unsigned)x : (unsigned)x;
  int started = 0;
  if (x < 0)
    uart_write(UART, '-');
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

static void print_vec(const char *label)
{
  uart_write_string(UART, label);
  for (int i = 0; i < N; i++)
  {
    print_int(vec[i]);
    uart_write(UART, ' ');
  }
  uart_write_string(UART, "\r\n");
}

void main(void)
{
  print_vec("Before: ");
  for (int i = 0; i < N - 1; i++)
    for (int j = 0; j < N - 1 - i; j++)
      if (vec[j] > vec[j + 1])
      {
        int t = vec[j];
        vec[j] = vec[j + 1];
        vec[j + 1] = t;
      }
  print_vec("After:  ");
}
