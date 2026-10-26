# Writes SE test vectors (op, A, B, C, expected value) as 128-bit hex lines.
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "host"))
import se  # noqa: E402

EDGE = [0, 1, -1, 2, -2, (1 << 63) - 1, -(1 << 63), 12345, -98765]


def main(path, count=120):
    rng = random.Random(551)
    lines = []
    for i in range(count):
        op = i % len(se.OPS)
        a, b, c = (rng.choice(EDGE) if rng.random() < 0.3 else rng.randint(-(1 << 62), 1 << 62)
                   for _ in range(3))
        if i % 12 == 5:
            c = 0
        expected = se.alu(op, a, b, c) & se.MASK64
        lines += [f"{op:032x}"] + [f"{se.encrypt(v):032x}" for v in (a, b, c)] + [f"{expected:032x}"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/sim/se_vectors.hex")
