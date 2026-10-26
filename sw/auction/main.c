#include "io.h"
#include "se.h"

#define MAX_BIDDERS 16

static ct_t bids[MAX_BIDDERS], ids[MAX_BIDDERS];
static char line[40];

static void read_line(void)
{
  int n = 0;
  for (;;)
  {
    while (!uart_data_received(UART))
      ;
    char ch = uart_read(UART);
    if (ch == '\n')
      break;
    if (ch != '\r' && n < (int)sizeof(line) - 1)
      line[n++] = ch;
  }
  line[n] = '\0';
}

static uint32_t hex_digit(char ch)
{
  if (ch >= '0' && ch <= '9')
    return ch - '0';
  if (ch >= 'a' && ch <= 'f')
    return ch - 'a' + 10;
  if (ch >= 'A' && ch <= 'F')
    return ch - 'A' + 10;
  return 0;
}

// Parses 32 hex digits, most significant word first, as printed by host/owner.py.
static void parse_ct(ct_t *c)
{
  for (int i = 0; i < 4; i++)
  {
    uint32_t w = 0;
    for (int k = 0; k < 8; k++)
      w = (w << 4) | hex_digit(line[8 * i + k]);
    c->w[3 - i] = w;
  }
}

void main(void)
{
  ct_t best, winner, gt, t;
  int n = 0;

  print_str("Sealed-bid auction\r\nready\r\n");

  // Protocol: number of bidders (public), then each bidder's encrypted bid and id.
  read_line();
  for (char *p = line; *p >= '0' && *p <= '9'; p++)
    n = n * 10 + (*p - '0');
  if (n < 1 || n > MAX_BIDDERS)
  {
    print_str("bad bidder count\r\ndone\r\n");
    return;
  }
  for (int i = 0; i < n; i++)
  {
    read_line();
    parse_ct(&bids[i]);
    read_line();
    parse_ct(&ids[i]);
  }

  for (int i = 0; i < n; i++)
  {
    print_str("bid ");
    print_uint(i);
    print_str(i < 10 ? "  " : " ");
    print_ct(&bids[i]);
    print_str("\r\n");
  }

  // Track the highest bid and its bidder without ever branching on a bid.
  ct_copy(&best, &bids[0]);
  ct_copy(&winner, &ids[0]);
  for (int i = 1; i < n; i++)
  {
    se_op(SE_LT, &best, &bids[i], &best, &gt);
    se_op(SE_CMOV, &bids[i], &best, &gt, &t);
    ct_copy(&best, &t);
    se_op(SE_CMOV, &ids[i], &winner, &gt, &t);
    ct_copy(&winner, &t);
  }

  print_str("winner ");
  print_ct(&winner);
  print_str("\r\nprice  ");
  print_ct(&best);
  print_str("\r\ndone\r\n");
}
