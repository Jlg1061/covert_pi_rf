import subprocess
import time
import binascii
import pigpio

# ============================================================
# Configuration
# ============================================================

GPIO_PINS = (4,20)

# GPIO clock frequency.
# Receiver listens to the 3rd harmonic near 40.68 MHz.
FREQ = 13_560_000


# ------------------------------------------------------------
# Manchester timing
# ------------------------------------------------------------

# Duration of one Manchester chip.
CHIP_TIME = 0.02


# ------------------------------------------------------------
# Fixed calibration timing
#
# These are intentionally NOT based on CHIP_TIME.
# Changing the Manchester data rate does not change how long
# we give the receiver to estimate RF OFF/ON levels.
# ------------------------------------------------------------

CAL_OFF_TIME = 2.0
CAL_ON_TIME = 3.0
GUARD_TIME = 1.5

# Silence after the message so receiver can recognize that
# the frame has ended and return to calibration mode.
END_SILENCE_TIME = 4


# ------------------------------------------------------------
# Frame configuration
# ------------------------------------------------------------

# Preamble is Manchester encoded but NOT Hamming encoded.
PREAMBLE = "1010101010101010"


# ============================================================
# Carrier control
# ============================================================

pi = pigpio.pi()

if not pi.connected:
    raise RuntimeError("Could not connect to pigpiod")

carrier_state = None


def carrier_on():
    global carrier_state

    if carrier_state == 1:
        return

    for gpio in GPIO_PINS:

        rc = pi.hardware_clock(
            gpio,
            FREQ
        )

        if rc != 0:

            # Stop anything that may already have been enabled
            for cleanup_gpio in GPIO_PINS:
                try:
                    pi.hardware_clock(
                        cleanup_gpio,
                        0
                    )
                    pi.set_mode(
                        cleanup_gpio,
                        pigpio.OUTPUT
                    )
                    pi.write(
                        cleanup_gpio,
                        0
                    )
                except Exception:
                    pass

            raise RuntimeError(
                f"hardware_clock ON failed "
                f"for GPIO{gpio}: {rc}"
            )

    carrier_state = 1

def carrier_off():
    global carrier_state

    if carrier_state == 0:
        return

    # GPIO4 and GPIO20 both use GPCLK0.
    # Disable the clock routing on both pins.
    for gpio in GPIO_PINS:

        rc = pi.hardware_clock(
            gpio,
            0
        )

        if rc != 0:
            raise RuntimeError(
                f"hardware_clock OFF failed "
                f"for GPIO{gpio}: {rc}"
            )

    # Explicitly drive both physical GPIO outputs LOW.
    for gpio in GPIO_PINS:

        pi.set_mode(
            gpio,
            pigpio.OUTPUT
        )

        pi.write(
            gpio,
            0
        )

    carrier_state = 0
# ============================================================
# Byte -> bits
# ============================================================

def bytes_to_bits(data):
    """
    Convert bytes into a string of binary digits.

    Example:

        b"A"

    becomes:

        01000001
    """

    return "".join(
        f"{byte:08b}"
        for byte in data
    )


# ============================================================
# Hamming(7,4)
# ============================================================

def hamming74_encode_nibble(bits):
    """
    Encode four bits using Hamming(7,4).

    Layout:

        Position:  1   2   3   4   5   6   7
                   p1  p2  d1  p4  d2  d3  d4

    Even parity:

        p1 = d1 XOR d2 XOR d4
        p2 = d1 XOR d3 XOR d4
        p4 = d2 XOR d3 XOR d4
    """

    if len(bits) != 4:
        raise ValueError(
            "Hamming nibble must contain exactly 4 bits"
        )

    d1 = int(bits[0])
    d2 = int(bits[1])
    d3 = int(bits[2])
    d4 = int(bits[3])

    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p4 = d2 ^ d3 ^ d4

    return (
        f"{p1}"
        f"{p2}"
        f"{d1}"
        f"{p4}"
        f"{d2}"
        f"{d3}"
        f"{d4}"
    )


def hamming74_encode(bits):
    """
    Encode an entire bit string with Hamming(7,4).

    Every:

        4 data bits

    become:

        7 encoded bits
    """

    if len(bits) % 4 != 0:
        raise ValueError(
            "Hamming input length must be divisible by 4"
        )

    result = []

    for i in range(
        0,
        len(bits),
        4
    ):

        nibble = bits[
            i:i + 4
        ]

        result.append(
            hamming74_encode_nibble(
                nibble
            )
        )

    return "".join(result)


# ============================================================
# Manchester encoding
# ============================================================

def manchester_encode(bits):
    """
    Manchester convention used by this project:

        0 -> 01
        1 -> 10

    Manchester chip:

        0 = carrier OFF
        1 = carrier ON
    """

    encoded = []

    for bit in bits:

        if bit == "0":

            encoded.extend(
                ["0", "1"]
            )

        elif bit == "1":

            encoded.extend(
                ["1", "0"]
            )

        else:

            raise ValueError(
                f"Invalid bit: {bit}"
            )

    return "".join(encoded)


# ============================================================
# CRC
# ============================================================

def calculate_crc(payload):
    """
    Calculate CRC-16 using Python's crc_hqx implementation.
    """

    return binascii.crc_hqx(
        payload,
        0xFFFF
    )


# ============================================================
# Frame construction
# ============================================================

def create_frame(message):

    # --------------------------------------------------------
    # UTF-8 payload
    # --------------------------------------------------------

    payload = message.encode(
        "utf-8"
    )

    if len(payload) > 65535:

        raise ValueError(
            "Message too large for 16-bit length field"
        )


    # --------------------------------------------------------
    # Length
    # --------------------------------------------------------

    length_bits = (
        f"{len(payload):016b}"
    )


    # --------------------------------------------------------
    # Payload
    # --------------------------------------------------------

    payload_bits = bytes_to_bits(
        payload
    )


    # --------------------------------------------------------
    # CRC-16
    # --------------------------------------------------------

    crc = calculate_crc(
        payload
    )

    crc_bits = (
        f"{crc:016b}"
    )


    # --------------------------------------------------------
    # Protected body
    #
    # 16-bit length
    # +
    # payload
    # +
    # 16-bit CRC
    #
    # This length is always divisible by four, so no padding
    # is necessary before Hamming(7,4).
    # --------------------------------------------------------

    body = (
        length_bits
        + payload_bits
        + crc_bits
    )


    # --------------------------------------------------------
    # Hamming(7,4)
    # --------------------------------------------------------

    hamming_body = hamming74_encode(
        body
    )


    # --------------------------------------------------------
    # Add preamble
    #
    # Preamble is deliberately NOT Hamming encoded.
    # --------------------------------------------------------

    frame_bits = (
        PREAMBLE
        + hamming_body
    )


    # --------------------------------------------------------
    # Manchester encode everything sent as frame data
    # --------------------------------------------------------

    manchester = manchester_encode(
        frame_bits
    )


    return {
        "payload": payload,
        "length_bits": length_bits,
        "payload_bits": payload_bits,
        "crc": crc,
        "crc_bits": crc_bits,
        "body": body,
        "hamming_body": hamming_body,
        "frame_bits": frame_bits,
        "manchester": manchester
    }


# ============================================================
# Receiver calibration
# ============================================================

def transmit_calibration():
    """
    Send a known RF calibration sequence.

        OFF for 2 seconds
        ON  for 3 seconds
        OFF for 1.5 seconds

    These times are independent of CHIP_TIME.
    """

    print(
        f"Calibration OFF "
        f"({CAL_OFF_TIME:.2f} s)"
    )

    carrier_off()

    time.sleep(
        CAL_OFF_TIME
    )


    print(
        f"Calibration ON "
        f"({CAL_ON_TIME:.2f} s)"
    )

    carrier_on()

    time.sleep(
        CAL_ON_TIME
    )


    print(
        f"Guard OFF "
        f"({GUARD_TIME:.2f} s)"
    )

    carrier_off()

    time.sleep(
        GUARD_TIME
    )


# ============================================================
# Manchester transmission
# ============================================================

def transmit_chips(encoded):
    """
    Transmit Manchester chips.

    Uses an absolute monotonic schedule instead of simply
    sleeping CHIP_TIME after each GPIO command. This reduces
    cumulative timing drift during long messages.
    """

    total = len(encoded)

    start_time = time.monotonic()


    for index, chip in enumerate(
        encoded,
        start=1
    ):

        # ----------------------------------------------------
        # Set current chip state
        # ----------------------------------------------------

        if chip == "1":

            carrier_on()

        else:

            carrier_off()


        # ----------------------------------------------------
        # Target absolute ending time for this chip
        # ----------------------------------------------------

        target_time = (
            start_time
            + index * CHIP_TIME
        )


        remaining = (
            target_time
            - time.monotonic()
        )


        if remaining > 0:

            time.sleep(
                remaining
            )


        # ----------------------------------------------------
        # Progress output
        # ----------------------------------------------------

        if (
            index % 20 == 0
            or index == total
        ):

            percent = (
                index
                / total
                * 100.0
            )

            print(
                f"\rTransmitting "
                f"{index}/{total} chips "
                f"({percent:.1f}%)",
                end="",
                flush=True
            )


    print()


# ============================================================
# Display frame information
# ============================================================

def print_frame_info(frame):

    print()
    print(
        "========================================"
    )

    print(
        "FRAME INFORMATION"
    )

    print(
        "========================================"
    )


    print(
        "Payload:"
    )

    print(
        repr(frame["payload"])
    )


    print(
        "Payload length:",
        len(frame["payload"]),
        "bytes"
    )


    print()
    print(
        "Length bits:"
    )

    print(
        frame["length_bits"]
    )


    print()
    print(
        "Payload bits:"
    )

    print(
        frame["payload_bits"]
    )


    print()
    print(
        "CRC-16:"
    )

    print(
        f"0x{frame['crc']:04X}"
    )

    print(
        "CRC bits:",
        frame["crc_bits"]
    )


    print()
    print(
        "Original protected body:",
        len(frame["body"]),
        "bits"
    )


    print(
        "Hamming encoded body:",
        len(frame["hamming_body"]),
        "bits"
    )


    print(
        "Preamble:",
        len(PREAMBLE),
        "bits"
    )


    print(
        "Total before Manchester:",
        len(frame["frame_bits"]),
        "bits"
    )


    print(
        "Manchester chips:",
        len(frame["manchester"])
    )


    # --------------------------------------------------------
    # Timing
    # --------------------------------------------------------

    calibration_time = (
        CAL_OFF_TIME
        + CAL_ON_TIME
        + GUARD_TIME
    )


    data_time = (
        len(frame["manchester"])
        * CHIP_TIME
    )


    total_time = (
        calibration_time
        + data_time
        + END_SILENCE_TIME
    )


    print()
    print(
        f"Calibration time: "
        f"{calibration_time:.2f} s"
    )

    print(
        f"Frame data time: "
        f"{data_time:.2f} s"
    )

    print(
        f"End silence: "
        f"{END_SILENCE_TIME:.2f} s"
    )

    print(
        f"Estimated total: "
        f"{total_time:.2f} s"
    )


    print(
        "========================================"
    )

    print()


def print_statistics(frame):
    payload_bits = len(frame["payload"]) * 8
    body_bits = len(frame["body"])
    hamming_bits = len(frame["hamming_body"])
    frame_bits = len(frame["frame_bits"])
    chips = len(frame["manchester"])

    calibration_time = (
        CAL_OFF_TIME
        + CAL_ON_TIME
        + GUARD_TIME
    )

    data_time = chips * CHIP_TIME

    total_time = (
        calibration_time
        + data_time
        + END_SILENCE_TIME
    )

    chip_rate = 1 / CHIP_TIME

    # Manchester requires 2 chips per encoded bit
    encoded_bit_rate = chip_rate / 2

    # Actual useful payload rate while frame data is being sent
    payload_rate_data_only = (
        payload_bits / data_time
        if data_time > 0
        else 0
    )

    # Actual useful payload rate including calibration/guard/end silence
    payload_goodput = (
        payload_bits / total_time
        if total_time > 0
        else 0
    )

    hamming_overhead = (
        ((hamming_bits / body_bits) - 1) * 100
        if body_bits > 0
        else 0
    )

    total_expansion = (
        chips / payload_bits
        if payload_bits > 0
        else 0
    )

    print()
    print("========================================")
    print("TRANSMISSION STATISTICS")
    print("========================================")

    print(f"Payload bytes:            {len(frame['payload'])}")
    print(f"Payload bits:             {payload_bits}")

    print(f"Protected body bits:      {body_bits}")
    print(f"Hamming encoded bits:     {hamming_bits}")
    print(f"Frame bits:               {frame_bits}")
    print(f"Manchester chips:         {chips}")

    print()
    print(f"Chip time:                {CHIP_TIME:.4f} s")
    print(f"Chip rate:                {chip_rate:.2f} chips/s")
    print(f"Manchester bit rate:      {encoded_bit_rate:.2f} bits/s")

    print()
    print(f"Frame transmission time:  {data_time:.2f} s")
    print(f"Total transmission time:  {total_time:.2f} s")

    print()
    print(f"Payload rate (data only): {payload_rate_data_only:.2f} bits/s")
    print(f"Payload goodput:          {payload_goodput:.2f} bits/s")

    print()
    print(f"Hamming overhead:         {hamming_overhead:.1f}%")
    print(f"Total expansion:          {total_expansion:.2f} chips/payload bit")

    print("========================================")
    print()


# ============================================================
# Main
# ============================================================

def main():

    message = input(
        "Message: "
    )


    # --------------------------------------------------------
    # Construct complete encoded frame
    # --------------------------------------------------------

    frame = create_frame(
        message
    )


    print_frame_info(
        frame
    )

    print_statistics(
        frame
    )

    try:

        print(
            "Starting transmission..."
        )


        # Always begin with carrier OFF.
        carrier_off()


        # ----------------------------------------------------
        # 1. Calibration
        # ----------------------------------------------------

        transmit_calibration()


        # ----------------------------------------------------
        # 2. Actual encoded frame
        # ----------------------------------------------------

        print(
            "Sending Manchester + "
            "Hamming(7,4) frame..."
        )

        transmit_chips(
            frame["manchester"]
        )


        # ----------------------------------------------------
        # 3. End silence
        # ----------------------------------------------------

        print(
            f"End-of-frame silence "
            f"({END_SILENCE_TIME:.2f} s)"
        )

        carrier_off()

        time.sleep(
            END_SILENCE_TIME
        )


    except KeyboardInterrupt:

        print()
        print(
            "Transmission interrupted."
        )


    finally:

        # Safety: never leave the GPIO hardware clock running.
        carrier_off()
        pi.stop()

    print(
        "Done."
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()
