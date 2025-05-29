import pigpio
import time

GPIO_RX = 27
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

print("📡 RF Jamming Detection Started (Threshold=2000 pulses/sec)... Ctrl+C to stop\n")

JAMMING_THRESHOLD = 2000  # تم زيادة الحد بوضوح

try:
    while True:
        pulse_count = 0
        time.sleep(1)

        pulses_per_second = pulse_count

        # تحديد حالة الجامينج الجديدة
        if pulses_per_second < JAMMING_THRESHOLD:
            jam_percentage = (pulses_per_second / JAMMING_THRESHOLD) * 100
            status = "✅ No Jamming (Safe)"
        else:
            jam_percentage = 100
            status = "🚨 High Jamming!"

        print(f"Pulses/sec: {pulses_per_second} | Jamming: {jam_percentage:.1f}% | Status: {status}")

except KeyboardInterrupt:
    print("\n🛑 Detection stopped.")
    pi.stop()


from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO
import time

# Setup screen
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_BL=18)
device = st7735(serial, width=128, height=128, rotation=0)

# Exit button GPIO
EXIT_PIN = 16
GPIO.setmode(GPIO.BCM)
GPIO.setup(EXIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

font = ImageFont.load_default()

def draw_screen(draw):
    draw.rectangle((0, 0, 128, 128), fill=(20, 20, 30))
    draw.text((10, 20), "🚨 Jamming Running", fill=(255, 100, 100), font=font)
    draw.text((10, 100), "Press to Exit", fill=(200, 200, 200), font=font)

try:
    while True:
        img = Image.new("RGB", (128, 128), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_screen(draw)
        device.display(img.rotate(-90))
        if GPIO.input(EXIT_PIN) == 0:
            break
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
