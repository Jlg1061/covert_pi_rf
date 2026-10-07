import subprocess
import time
import binascii


# ============================================================
# Configuration
# ============================================================

GPIO = 4

# Generate 13.56 MHz on GPIO4.
# Receiver listens to the 3rd harmonic around 40.68 MHz.
FREQ = 13_560_000

# Duration of one Manchester chip / half-bit
CHIP_TIME = 0.25

# Repetition-code factor
REPEAT = 3

# Calibration sequence
CAL_OFF_CHIPS = 6
CAL_ON_CHIPS = 8
GUARD_CHIPS = 5

# Silence after transmission so receiver can reset
END_SILENCE_CHIPS = 10

# Raw-bit preamble.
# This is NOT repetition encoded.
PREAMBLE = "1010101010101010"


# ============================================================
# Carrier control
# ============================================================

def clock(freq):
    subprocess.run(
        [
            "pigs",
            "hc",
            str(GPIO),
            str(freq)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def carrier_on():
    clock(FREQ)


def carrier_off():
    clock(0)


# ============================================================
# Bit conversion
# ============================================================

def bytes_to_bits(data):
    """
    Convert bytes into a string of 0/1 bits.
    """
    return "".join(
        f"{byte:08b}"
        for byte in data
    )


# ============================================================
# Forward Error Correction
# ============================================================

def repetition_encode(bits, repeat=REPEAT):
    """
    Repetition-3 example:

        0 -> 000
        1 -> 111
    """

    return "".join(
        bit * repeat
        for bit in bits
    )


# ============================================================
# Manchester encoding
# ============================================================

def manchester_encode(bits):
    """
    Manchester convention:

        0 -> 01
        1 -> 10

    Manchester chip:

        0 = carrier OFF
        1 = carrier ON
    """

    encoded = []

    for bit in bits:

        if bit == "0":
            encoded.extend(["0", "1"])

        elif bit == "1":
            encoded.extend(["1", "0"])

        else:
            raise ValueError(
                f"Invalid bit: {bit}"
            )

    return "".join(encoded)


# ============================================================
# Frame construction
# ============================================================

def create_frame(message):

    # Encode message as UTF-8
    payload = message.encode("utf-8")

    # --------------------------------------------------------
    # Length
    # --------------------------------------------------------

    # Length is number of payload BYTES
    if len(payload) > 65535:
        raise ValueError(
            "Message is too large for the 16-bit length field"
        )

    length_bits = f"{len(payload):016b}"


    # --------------------------------------------------------
    # Payload
    # --------------------------------------------------------

    payload_bits = bytes_to_bits(payload)


    # --------------------------------------------------------
    # CRC-16
    # --------------------------------------------------------

    crc = binascii.crc_hqx(
        payload,
        0xFFFF
    )

    crc_bits = f"{crc:016b}"


    # --------------------------------------------------------
    # Protected body
    #
    # Length + Payload + CRC are repetition encoded.
    # --------------------------------------------------------

    body = (
        length_bits
        + payload_bits
        + crc_bits
    )

    protected_body = repetition_encode(
        body,
        REPEAT
    )


    # --------------------------------------------------------
    # Preamble is NOT repetition encoded.
    # --------------------------------------------------------

    frame_bits = (
        PREAMBLE
        + protected_body
    )


    # --------------------------------------------------------
    # Manchester encode entire transmitted frame
    # --------------------------------------------------------

    manchester = manchester_encode(
        frame_bits
    )


    return {
        "payload": payload,
        "payload_bits": payload_bits,
        "length_bits": length_bits,
        "crc": crc,
        "crc_bits": crc_bits,
        "body": body,
        "protected_body": protected_body,
        "frame_bits": frame_bits,
        "manchester": manchester,
    }


# ============================================================
# Calibration sequence
# ============================================================

def transmit_calibration():

    print("Calibration: OFF")

    carrier_off()

    time.sleep(
        CAL_OFF_CHIPS
        * CHIP_TIME
    )


    print("Calibration: ON")

    carrier_on()

    time.sleep(
        CAL_ON_CHIPS
        * CHIP_TIME
    )


    print("Calibration: OFF guard")

    carrier_off()

    time.sleep(
        GUARD_CHIPS
        * CHIP_TIME
    )


# ============================================================
# Manchester transmission
# ============================================================

def transmit_chips(encoded):

    total = len(encoded)

    for index, chip in enumerate(
        encoded,
        start=1
    ):

        if chip == "1":
            carrier_on()

        else:
            carrier_off()

        time.sleep(CHIP_TIME)

        # Optional progress display
        if (
            index % 20 == 0
            or index == total
        ):

            print(
                f"\rTransmitting chip "
                f"{index}/{total}",
                end="",
                flush=True
            )

    print()


# ============================================================
# Main
# ============================================================

def main():

    message = input("Message: ")

    frame = create_frame(message)


    print()
    print("==============================")
    print("TRANSMISSION INFORMATION")
    print("==============================")

    print(
        "Payload bytes:",
        len(frame["payload"])
    )

    print(
        "Payload bits:",
        frame["payload_bits"]
    )

    print(
        "Length bits:",
        frame["length_bits"]
    )

    print(
        "CRC-16:",
        f"0x{frame['crc']:04X}"
    )

    print(
        "CRC bits:",
        frame["crc_bits"]
    )

    print(
        "Original protected body bits:",
        len(frame["body"])
    )

    print(
        "After repetition-3:",
        len(frame["protected_body"])
    )

    print(
        "Frame bits before Manchester:",
        len(frame["frame_bits"])
    )

    print(
        "Manchester chips:",
        len(frame["manchester"])
    )


    data_time = (
        len(frame["manchester"])
        * CHIP_TIME
    )

    calibration_time = (
        CAL_OFF_CHIPS
        + CAL_ON_CHIPS
        + GUARD_CHIPS
    ) * CHIP_TIME

    ending_time = (
        END_SILENCE_CHIPS
        * CHIP_TIME
    )

    total_time = (
        calibration_time
        + data_time
        + ending_time
    )


    print(
        f"Estimated frame time: "
        f"{total_time:.2f} seconds"
    )

    print()
    print("Starting transmission...")


    try:

        # Make absolutely sure carrier starts OFF
        carrier_off()

        # --------------------------------------------
        # Receiver calibration
        # --------------------------------------------

        transmit_calibration()


        # --------------------------------------------
        # Manchester frame
        # --------------------------------------------

        print("Sending Manchester frame")

        transmit_chips(
            frame["manchester"]
        )


        # --------------------------------------------
        # End-of-frame silence
        # --------------------------------------------

        print("End silence")

        carrier_off()

        time.sleep(
            END_SILENCE_CHIPS
            * CHIP_TIME
        )


    except KeyboardInterrupt:

        print()
        print("Transmission interrupted.")


    finally:

        # Always shut the GPIO hardware clock off
        carrier_off()


    print("Done.")


if __name__ == "__main__":
    main()
