from rpi_rf import RFDevice
import time

GPIO_PIN = 20

rfdevice = RFDevice(GPIO_PIN)
rfdevice.enable_tx()

try:
    code = 809999
    print("📤 Sending code:", code)
    rfdevice.tx_code(code)  # بدون تحديد protocol أو length
    print("✅ Done sending.")

except KeyboardInterrupt:
    print("🛑 Aborted.")

finally:
    rfdevice.cleanup()


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
