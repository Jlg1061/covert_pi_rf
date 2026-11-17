# Design decisions and system operation

*Rationale and interpretation of the cable-free proof of concept*

## Project objective and threat model

Our project asks whether a Raspberry Pi can communicate through the electromagnetic side effects of hardware that it already contains. The transmitter runs software that controls the GPIO clock peripheral, while a separate receiver observes the resulting emissions. The main constraint is that **nothing is connected to the transmitting GPIO pins**: there is no attached antenna, wire, or external RF circuit. During development, connecting a wire produced a much clearer signal, but retaining that wire would change the experiment from unintended board emissions to a deliberately improved radiator. We therefore treat wire-assisted tests as diagnostics rather than evidence for the cable-free threat model. This PoC assumes that code can already execute on the Pi; it does not demonstrate how that execution would be obtained.

## Message construction and transmission

The sender first converts the input message to UTF-8 bytes. It constructs a body containing a **16-bit payload length**, the payload, and a **16-bit CRC** calculated over the payload. The body is then protected with **Hamming(7,4)** coding, which adds redundancy for error correction. A known 16-bit alternating preamble is placed before the protected body. Finally, Manchester encoding maps a zero to an OFF–ON chip pair and a one to an ON–OFF pair. We chose Manchester because a transition within each bit aids timing recovery and lets the receiver compare neighboring intervals even when the absolute power baseline changes. The cost is twice as many transmitted chips per encoded bit, on top of the Hamming overhead; the CRC detects residual errors rather than correcting them.

Before the data, the transmitter sends **2 s OFF, 3 s ON, and a 1.5 s OFF guard**; after the frame it leaves the clock off for 4 s. These intervals help separate the message from the surrounding background and provide calibration observations. Chip boundaries are scheduled against a monotonic clock to reduce accumulated drift, but Linux and pigpio do not provide a hard real-time guarantee. The repository’s 100 ms chip setting is a conservative operating point for the weak-signal experiment, not a measured maximum transmission rate.

## How the receiver recovers the message

The RTL-SDR samples at **1 MS/s** while tuned to 40.58 MHz, putting the expected 40.68 MHz component 100 kHz from the tuning center. GNU Radio translates that component to baseband, applies frequency-selective filtering, and decimates the stream. A second low-pass filter with a 2 kHz cutoff reduces out-of-band noise before computing signal power. Moving-average smoothing and further decimation produce approximately **100 power samples/s**, or 10 samples per 100 ms chip.

The cable-free flowgraph uses a **differential Manchester decoder** instead of first converting each sample to a hard ON/OFF decision. It searches for the known preamble across possible chip alignments and averages the middle portion of each chip. For a chip pair it computes \(D = P_{\mathrm{second}} - P_{\mathrm{first}}\): positive \(D\) favors zero and negative \(D\) favors one. These relative measurements are also used for soft-decision Hamming decoding. After reconstructing the declared payload length, the receiver checks the CRC before publishing text. This approach is intended to be more tolerant of weak amplitude differences, but it still depends on accurate chip timing, receiver tuning, and sufficient separation from noise.

## Current scope and evaluation

We have observed the cable-free signal only at favorable receiving-antenna orientations, and narrower filtering improved reception in the bench setup. The repository does **not yet establish a maximum reliable distance**, calibrated RF power, or a bit/packet error rate. The next evaluation will hold transmitter settings and SDR gain fixed, then vary separation and antenna orientation. Repeated transmissions, CRC-validated success rate, and received signal-to-noise measurements will distinguish a visible RF component from a reliably decoded channel. Absolute dBm values should not be claimed without calibrating the SDR measurement chain.

---

# Covert Pi RF

*PoC / Quick Start*

[github.com/Jlg1061/covert_pi_rf](https://github.com/Jlg1061/covert_pi_rf)

A proof of concept for a **software-controlled electromagnetic covert channel** on a Raspberry Pi 4. The transmitter toggles the **13.56 MHz GPCLK0** output on GPIO4 and GPIO20; a separate RTL-SDR observes incidental emissions near the **40.68 MHz third harmonic**. The intended threat model requires **no antenna, cable, or load attached to either GPIO pin**.

## Requirements

- **Transmitter:** Raspberry Pi 4, Python 3, pigpio Python package and running `pigpiod` daemon.
- **Receiver:** RTL-SDR Blog V4 (or compatible SDR), receiving loop/probe, GNU Radio Companion 3.10 with RTL-SDR source support.
- **Files:** `GPIO_experiment/2gpio_sender.py` (TX) and `gnu_radio/lpf_nocabletest.grc` (RX).

## Quick start

1. **Clone the repository** on both the Pi and the receiver host.

   ```bash
   git clone https://github.com/Jlg1061/covert_pi_rf.git
   cd covert_pi_rf
   ```

2. **Start the receiver first.** Connect the receiving antenna to the RTL-SDR, then open and run the GNU Radio flowgraph.

   ```bash
   gnuradio-companion gnu_radio/lpf_nocabletest.grc
   ```

3. **Transmit from the Pi.** On the Pi, start the daemon, run the sender, and enter a short UTF-8 message at the prompt.

   ```bash
   sudo pigpiod
   python3 GPIO_experiment/2gpio_sender.py
   ```

4. **Verify reception.** Check GNU Radio’s power-envelope plot and Message Debug output for the recovered text. Keep the GPIO pins bare during the cable-free experiment.

## How it works

**Processing chain:** Pi GPCLK0 → third-harmonic RF → RTL-SDR → frequency translation and low-pass filtering → power detection → differential Manchester decoder → Hamming correction / CRC check.

**Frame format:** 2 s OFF, 3 s ON calibration, 1.5 s OFF guard; then a 16-bit preamble followed by Hamming(7,4)-encoded `16-bit payload length | UTF-8 payload | CRC-16`. Manchester encoding maps bit 0 to `01` (OFF/ON) and bit 1 to `10` (ON/OFF). The sender finishes with 4 s OFF silence.

## Default settings

| Transmitter | Value | Receiver | Value |
|---|---|---|---|
| GPIO pins / clock | 4 + 20 / 13.56 MHz | SDR tune / target | 40.58 / 40.68 MHz |
| Chip duration | 0.10 s | Input sample rate | 1 MS/s |
| Modulation | OOK + Manchester | Frequency shift | +100 kHz |
| FEC / integrity | Hamming(7,4) + CRC-16 | LPF / output rate | 2 kHz / 100 S/s |

**Important:** Set the same `CHIP_TIME` on the Pi and `chip_time` in GNU Radio; the repository defaults above are a known starting configuration, not a measured maximum rate.

## Troubleshooting and limitations

- **No RF peak:** Confirm third-harmonic tuning near 40.68 MHz; sweep the receiving antenna’s position and orientation; use fixed RTL-SDR gain.
- **Peak but no message:** Confirm matched chip times; start the receiver before the sender; inspect preamble alignment and decoder logs.
- **Dropped samples (O):** Reduce GUI/display overhead and check receiver sample-rate and decimation settings.

**Scope:** Bench PoC only; the repository does not establish reliable range, BER/PER, or calibrated received power. Measure these experimentally. Use only on authorized lab hardware.
