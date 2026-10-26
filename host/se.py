# Reference model of the SE unit: SIMON-128/128 plus the encrypted operations.
import secrets

MASK64 = (1 << 64) - 1
ROUNDS = 68
Z2 = "10101111011100000011010010011000101000010001111110010110110011"

# Demo key; must match KEY in hw/se_unit.v.
KEY = 0x2B7E151628AED2A6ABF7158809CF4F3C

OPS = {"ADD": 0, "SUB": 1, "MUL": 2, "LT": 3, "EQ": 4, "CMOV": 5}


def _rol(x, r):
    return ((x << r) | (x >> (64 - r))) & MASK64


def _ror(x, r):
    return ((x >> r) | (x << (64 - r))) & MASK64


def _f(x):
    return (_rol(x, 1) & _rol(x, 8)) ^ _rol(x, 2)


def round_keys(key):
    k = [key & MASK64, key >> 64]
    for i in range(2, ROUNDS):
        tmp = _ror(k[i - 1], 3)
        tmp ^= _ror(tmp, 1)
        k.append((~k[i - 2] & MASK64) ^ tmp ^ int(Z2[(i - 2) % 62]) ^ 3)
    return k


def simon_encrypt(block, key):
    x, y = block >> 64, block & MASK64
    for rk in round_keys(key):
        x, y = y ^ _f(x) ^ rk, x
    return (x << 64) | y


def simon_decrypt(block, key):
    x, y = block >> 64, block & MASK64
    for rk in reversed(round_keys(key)):
        x, y = y, x ^ _f(y) ^ rk
    return (x << 64) | y


def to_signed(v):
    return v - (1 << 64) if v >> 63 else v


def encrypt(value, key=KEY, salt=None):
    salt = secrets.randbits(64) if salt is None else salt
    return simon_encrypt(((value & MASK64) << 64) | salt, key)


def decrypt(ct, key=KEY):
    return to_signed(simon_decrypt(ct, key) >> 64)


def alu(op, a, b, c=0):
    a, b, c = a & MASK64, b & MASK64, c & MASK64
    if op == OPS["ADD"]:
        r = a + b
    elif op == OPS["SUB"]:
        r = a - b
    elif op == OPS["MUL"]:
        r = a * b
    elif op == OPS["LT"]:
        r = int(to_signed(a) < to_signed(b))
    elif op == OPS["EQ"]:
        r = int(a == b)
    elif op == OPS["CMOV"]:
        r = a if c else b
    else:
        raise ValueError(f"unknown opcode {op}")
    return to_signed(r & MASK64)


def se_op(op, ct_a, ct_b, ct_c=0, key=KEY):
    return encrypt(alu(op, decrypt(ct_a, key), decrypt(ct_b, key), decrypt(ct_c, key)), key)
