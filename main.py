import subprocess
from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from PIL import Image, ImageDraw, ImageFont
import smbus
import time
import RPi.GPIO as GPIO
import math
from datetime import datetime

# GPIO setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
SW_PIN = 16
GPIO.setup(SW_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# I2C setup for ADC
bus = smbus.SMBus(1)
adc_address = 0x48

# Display setup
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_BL=18)
device = st7735(serial, width=128, height=128, rotation=0)

# Font loading
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
except:
    font = title_font = small_font = ImageFont.load_default()

# Color scheme
COLOR_BG = (30, 30, 40)
COLOR_ACCENT = (0, 200, 180)
COLOR_WARNING = (255, 100, 0)
COLOR_TEXT = (220, 220, 220)
COLOR_HIGHLIGHT = (50, 50, 70)
COLOR_ACTIVE = (0, 255, 100)

# Joystick functions
def read_channel(channel):
    try:
        bus.write_byte(adc_address, 0x40 | channel)
        bus.read_byte(adc_address)
        return bus.read_byte(adc_address)
    except:
        return 128

def calibrate_joystick(samples=50):
    sum_x = sum_y = 0
    for _ in range(samples):
        sum_x += read_channel(0)
        sum_y += read_channel(1)
        time.sleep(0.01)
    return sum_x // samples, sum_y // samples

def get_direction(x, y, cx, cy, threshold=15):
    dx = x - cx
    dy = y - cy
    if abs(dx) < threshold and abs(dy) < threshold:
        return 0
    if abs(dx) > abs(dy):
        return 1 if dx > 0 else 2
    else:
        return 3 if dy > 0 else 4

# Drawing functions
def draw_menu(draw, selected_item):
    draw.rectangle((0, 0, 128, 128), fill=COLOR_BG)
    draw.text((10, 5), "RF Security Menu", font=title_font, fill=COLOR_ACCENT)
    options = ["Jamming", "Detect", "TX", "RX24", "RX32", "RX64", "RX128"]
    for i, opt in enumerate(options):
        y = 25 + i * 15
        color = COLOR_WARNING if i == selected_item else COLOR_TEXT
        draw.text((10, y), opt, font=font, fill=color)

# Main loop
if __name__ == "__main__":
    center_x, center_y = calibrate_joystick()
    selected_item = 0
    last_move = time.time()
    last_btn = GPIO.input(SW_PIN)

    while True:
        x = read_channel(0)
        y = read_channel(1)
        btn = GPIO.input(SW_PIN)
        direction = get_direction(x, y, center_x, center_y)

        if time.time() - last_move > 0.3:
            if direction == 3:
                selected_item = (selected_item + 1) % 7
                last_move = time.time()
            elif direction == 4:
                selected_item = (selected_item - 1) % 7
                last_move = time.time()

        if last_btn == 1 and btn == 0:
            script_map = ["Jamming.py", "Jammingdetect.py", "transmeter.py",
                          "recever24.py", "recever32.py", "recever64.py", "recever128.py"]
            subprocess.Popen(["python3", script_map[selected_item]])

        last_btn = btn

        img = Image.new("RGB", (128, 128), COLOR_BG)
        draw = ImageDraw.Draw(img)
        draw_menu(draw, selected_item)
        device.display(img.rotate(-90))
        time.sleep(0.1)
