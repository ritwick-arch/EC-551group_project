import random

import se


def test_simon_official_vector():
    key = 0x0F0E0D0C0B0A09080706050403020100
    pt = 0x63736564207372656C6C657661727420
    assert se.simon_encrypt(pt, key) == 0x49681B1E1E54FE3F65AA832AF84E0BBC
    assert se.simon_decrypt(0x49681B1E1E54FE3F65AA832AF84E0BBC, key) == pt


def test_roundtrip_and_salting():
    for v in [0, 1, -1, 42, -(1 << 63), (1 << 63) - 1]:
        assert se.decrypt(se.encrypt(v)) == v
    assert len({se.encrypt(5) for _ in range(5)}) == 5


def test_ops():
    rng = random.Random(1)
    for _ in range(200):
        a, b, c = (rng.randint(-(1 << 40), 1 << 40) for _ in range(3))
        ca, cb, cc = se.encrypt(a), se.encrypt(b), se.encrypt(c)
        ops = se.OPS
        assert se.decrypt(se.se_op(ops["ADD"], ca, cb)) == a + b
        assert se.decrypt(se.se_op(ops["SUB"], ca, cb)) == a - b
        assert se.decrypt(se.se_op(ops["MUL"], ca, cb)) == se.to_signed((a * b) & se.MASK64)
        assert se.decrypt(se.se_op(ops["LT"], ca, cb)) == int(a < b)
        assert se.decrypt(se.se_op(ops["EQ"], ca, ca)) == 1
        assert se.decrypt(se.se_op(ops["CMOV"], ca, cb, cc)) == (a if c else b)
