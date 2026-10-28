#include "io.h"
#include "se.h"

#define MAX_BIDDERS 16

static ct_t bids[MAX_BIDDERS], ids[MAX_BIDDERS];
static char line[40];

void main(void)
{
  ct_t best, winner, gt, t;
  int n;

  print_str("Sealed-bid auction\r\nready\r\n");

  // Protocol: number of bidders (public), then each bidder's encrypted bid and id.
  read_line(line, sizeof line);
  n = parse_int(line);
  if (n < 1 || n > MAX_BIDDERS)
  {
    print_str("bad bidder count\r\ndone\r\n");
    return;
  }
  for (int i = 0; i < n; i++)
  {
    read_line(line, sizeof line);
    parse_ct(line, &bids[i]);
    read_line(line, sizeof line);
    parse_ct(line, &ids[i]);
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
