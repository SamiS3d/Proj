import pigpio
import time
import random
import signal
import sys

GPIO_TX = 20
pi = pigpio.pi()

if not pi.connected:
    exit("❌ Run sudo pigpiod first!")

pi.set_mode(GPIO_TX, pigpio.OUTPUT)

running = True

def smooth_shutdown(signal, frame):
    global running
    print("\n🔻 Starting smooth shutdown...")
    running = False  # إيقاف حلقة الجامينج بلطف

signal.signal(signal.SIGINT, smooth_shutdown)

def rf_jamming():
    global running
    print("🚨 RF Jamming started at 433MHz (Press Ctrl+C to stop smoothly)...")

    wave_ids = []

    try:
        while running:
            pulse_duration = random.randint(50, 500)
            pi.wave_clear()

            pulses = [
                pigpio.pulse(1 << GPIO_TX, 0, pulse_duration),
                pigpio.pulse(0, 1 << GPIO_TX, pulse_duration)
            ]

            pi.wave_add_generic(pulses)
            wave_id = pi.wave_create()

            if wave_id >= 0:
                wave_ids.append(wave_id)
                pi.wave_send_repeat(wave_id)
                time.sleep(0.01)
                pi.wave_delete(wave_id)

        # مرحلة الإغلاق الناعم (Smooth shutdown)
        for i in range(5, 0, -1):
            pulse_duration = i * 200  # زيادة مدة النبضة تدريجيًا (خفض قوة الإشارة)
            pi.wave_clear()

            pulses = [
                pigpio.pulse(1 << GPIO_TX, 0, pulse_duration),
                pigpio.pulse(0, 1 << GPIO_TX, pulse_duration)
            ]

            pi.wave_add_generic(pulses)
            wave_id = pi.wave_create()

            if wave_id >= 0:
                pi.wave_send_repeat(wave_id)
                print(f"🔻 Reducing Jamming power... Step {6 - i}/5")
                time.sleep(0.5)  # وقت كافي لتخفيف التشويش
                pi.wave_delete(wave_id)

        # إيقاف نهائي بشكل واضح
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX, 0)  # إغلاق GPIO بشكل كامل
        pi.stop()

        print("✅ RF Jamming stopped smoothly. Receiver is safe now.")

    except Exception as e:
        print(f"⚠️ Error: {e}")
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX, 0)
        pi.stop()

if __name__ == "__main__":
    rf_jamming()



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
