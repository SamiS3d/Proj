import pigpio
import time
import sys
import os

# تحديد المسار الأساسي
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# وظيفة لحفظ الرموز في ملف (من الكود الأول)
def save_key(key):
    count = get_saved_keys_count() + 1
    kar_name = f"kar{count}"
    with open(os.path.join(BASE_DIR, "keys.txt"), "a") as f:
        f.write(f"{kar_name}:{key}\n")
    return kar_name

# وظيفة لقراءة عدد الرموز المحفوظة (من الكود الأول)
def get_saved_keys_count():
    try:
        with open(os.path.join(BASE_DIR, "keys.txt"), "r") as f:
            return len(f.readlines())
    except FileNotFoundError:
        return 0

GPIO_PIN = 21
pi = pigpio.pi()
if not pi.connected:
    exit("❌ Failed to connect to pigpio! Run: sudo pigpiod")

pi.set_mode(GPIO_PIN, pigpio.INPUT)
pi.set_pull_up_down(GPIO_PIN, pigpio.PUD_DOWN)

timings = []
last_tick = None
last_bits = ""
last_bits_time = 0
MIN_PULSES = 10
MAX_STD_DEV = 1200
MIN_BITS_LEN = 23
MAX_BITS_LEN = 25
REPEAT_SUPPRESSION_MS = 100

def decode_bits(bits):
    try:
        decimal_value = int(bits, 2)
        hex_value = hex(decimal_value)
        return decimal_value, hex_value
    except ValueError:
        return None, None

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

def get_stddev(data):
    mean = sum(data) / len(data)
    variance = sum((x - mean) ** 2 for x in data) / len(data)
    return variance ** 0.5

def filter_outliers(data, std_multiplier=2):
    if len(data) < 2:
        return data
    mean = sum(data) / len(data)
    stddev = get_stddev(data)
    return [x for x in data if (mean - std_multiplier * stddev) <= x <= (mean + std_multiplier * stddev)]

def timings_to_bits(timings):
    bits = ""
    filtered_timings = filter_outliers(timings)

    highs = filtered_timings[::2]
    lows = filtered_timings[1::2]

    if len(highs) < 2 or len(lows) < 2:
        return None

    avg_high = sum(highs) / len(highs)
    avg_low = sum(lows) / len(lows)

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
                # حفظ الرمز في ملف keys.txt
                key_name = save_key(output)
                print(f"✅ Key saved as {key_name}: {output}")
                sys.stdout.flush()
                last_bits = bits
                last_bits_time = now_time

# إعداد الاستماع
pi.callback(GPIO_PIN, pigpio.EITHER_EDGE, rf_callback)
pi.set_watchdog(GPIO_PIN, 10)

try:
    print("📡 Listening (Filtered + Dedup)... Ctrl+C to stop")
    sys.stdout.flush()
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n🛑 Stopped.")
    pi.stop()