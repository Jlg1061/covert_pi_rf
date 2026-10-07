#!/usr/bin/env python3

import subprocess
import time

GPIO = 4
FREQ = 13_560_000
SYMBOL = 0.100

def clock(freq):
    subprocess.run(
        ["pigs", "hc", str(GPIO), str(freq)],
        check=True,
        stdout=subprocess.DEVNULL
    )

# Known laboratory test pattern, not sensitive data.
bits = "1010101010101010" + "1100110011001100"

try:
    for bit in bits:
        clock(FREQ if bit == "1" else 0)
        time.sleep(SYMBOL)
finally:
    clock(0)
