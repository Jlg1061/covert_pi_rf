import subprocess
import time

GPIO = 4
FREQ = 13_560_000

def clock(freq):
    subprocess.run(["pigs", "hc", str(GPIO), str(freq)])

try:
    while True:
        print("OFF")
        clock(0)
        time.sleep(5)

        print("ON")
        clock(FREQ)
        time.sleep(5)

finally:
    clock(0)
