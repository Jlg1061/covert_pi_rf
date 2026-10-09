import subprocess
import time

GPIO = 4
FREQ = 13_560_000

# Duration of each Manchester half-bit
CHIP_TIME = 1


def clock(freq):
    subprocess.run(
        ["pigs", "hc", str(GPIO), str(freq)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def carrier_on():
    clock(FREQ)


def carrier_off():
    clock(0)


def text_to_bits(message):
    return "".join(f"{byte:08b}" for byte in message.encode("utf-8"))


def manchester_encode(bits):
    """
    Manchester convention used here:

    0 -> 01
    1 -> 10

    0 = carrier OFF
    1 = carrier ON
    """
    encoded = ""

    for bit in bits:
        if bit == "0":
            encoded += "01"
        else:
            encoded += "10"

    return encoded


def transmit(encoded):
    for chip in encoded:
        if chip == "1":
            carrier_on()
        else:
            carrier_off()

        time.sleep(CHIP_TIME)


def main():
    message = input("Message: ")

    bits = text_to_bits(message)

    # Add a simple length field
    length = len(message.encode("utf-8"))
    length_bits = f"{length:016b}"

    # Known synchronization pattern
    preamble = "1010101010101010"

    frame = preamble + length_bits + bits

    encoded = manchester_encode(frame)

    print("Binary:")
    print(bits)

    print("\nManchester:")
    print(encoded)

    print("\nTransmitting...")

    try:
        PREAMBLE_SILENCE_CHIPS = 5
        carrier_off()

        # Initial silence
        time.sleep(PREAMBLE_SILENCE_CHIPS * CHIP_TIME)

        # Calibration
        CAL_OFF_CHIPS = 6
        CAL_ON_CHIPS = 8
        GUARD_CHIPS = 5
        END_SILENCE_CHIPS = 10

        carrier_off()
        time.sleep(CAL_OFF_CHIPS * CHIP_TIME)

        carrier_on()
        time.sleep(CAL_ON_CHIPS * CHIP_TIME)

        carrier_off()
        time.sleep(GUARD_CHIPS * CHIP_TIME)

        transmit(encoded)

        carrier_off()
        time.sleep(END_SILENCE_CHIPS * CHIP_TIME)
      

    finally:
        carrier_off()

    print("Done.")


if __name__ == "__main__":
    main()
