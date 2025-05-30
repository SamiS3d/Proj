import pigpio
import time
import sys

GPIO_RX = 21
pi = pigpio.pi()

if not pi.connected:
    exit("❌ Run sudo pigpiod first!")

pi.set_mode(GPIO_RX, pigpio.INPUT)
pi.set_pull_up_down(GPIO_RX, pigpio.PUD_DOWN)

pulse_count = 0

def rf_callback(gpio, level, tick):
    global pulse_count
    pulse_count += 1

pi.callback(GPIO_RX, pigpio.EITHER_EDGE, rf_callback)

sys.stdout.flush()

JAMMING_THRESHOLD = 2000  # تم زيادة الحد بوضوح

try:
    while True:
        pulse_count = 0
        time.sleep(1)

        pulses_per_second = pulse_count

        # تحديد حالة الجامينج الجديدة
        if pulses_per_second < JAMMING_THRESHOLD:
            jam_percentage = (pulses_per_second / JAMMING_THRESHOLD) * 100
            status = "No Jamming"
        else:
            jam_percentage = 100
            status = "High Jamming!"

        output = f"J:{jam_percentage:.1f}% | S:{status}"
        print(output)
        sys.stdout.flush()  # ✅ ضروري لعرضها في شاشة TFT عبر subprocess في main.py

except KeyboardInterrupt:
    print("\n🛑 Detection stopped.")
    sys.stdout.flush()
    pi.stop()
