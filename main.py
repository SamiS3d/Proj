import time
import smbus2
import RPi.GPIO as GPIO
import subprocess
import signal
import os
from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from luma.core.render import canvas
from PIL import Image, ImageDraw, ImageFont

# Initialize ST7735 display
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_CS=8)
device = st7735(serial, width=128, height=128, rotate=1)
device.backlight(True)

# GPIO and I2C setup for joystick
GPIO.setmode(GPIO.BCM)
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
bus = smbus2.SMBus(1)
ADS1115_ADDRESS = 0x48

# ADS1115 configuration
def read_adc(channel):
    try:
        config = 0xC183 | (channel << 12)
        bus.write_i2c_block_data(ADS1115_ADDRESS, 0x01, [(config >> 8) & 0xFF, config & 0xFF])
        time.sleep(0.01)
        data = bus.read_i2c_block_data(ADS1115_ADDRESS, 0x00, 2)
        value = (data[0] << 8) | data[1]
        print(f"Channel {channel}: {value}")
        return value
    except Exception as e:
        print(f"ADC read error on channel {channel}: {e}")
        return 0

# Colors (RGB)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)
GRAY = (100, 100, 100)

# Fonts
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except IOError:
    font = ImageFont.load_default()
    small_font = ImageFont.load_default()

# Menu structure
main_menu = ["Info", "Security part", "Attack part", "Wifi Test"]
security_menu = ["Jamming Detection", "Captcher My RF kye", "Captcher My RF kye Rolling", "Reuse My RF kye", "Exit"]
attack_menu = ["Jamming", "Captcher RF kye", "Captcher RF kye Rolling", "Reuse My RF kye", "Exit"]
capture_menu = ["24BIT", "32BIT", "64BIT", "128BIT", "Exit"]

# State variables
current_menu = "main"
selected_index = 0
current_page = None
last_button_state = True
last_move_time = 0
move_delay = 0.2
jamming_process = None
jamming_active = False
capture_process = None
capture_active = False
capture_bit = None

def draw_menu(draw, items, selected):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    for i, item in enumerate(items):
        y = 20 + i * 25
        if i == selected:
            draw.rectangle((10, y - 2, 117, y + 16), fill=GRAY)
            draw.text((15, y), item, font=font, fill=BLUE)
        else:
            draw.text((15, y), item, font=font, fill=WHITE)

def draw_info_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    lines = [
        "Graduation Project",
        "Cybersecurity",
        "Requirement",
        "By: Sami Saad",
        "Ahmed Rashid",
        "Exit"
    ]
    for i, line in enumerate(lines):
        y = 10 + i * 18
        color = BLUE if i == len(lines) - 1 and selected_index == 0 else WHITE
        draw.text((10, y), line, font=small_font, fill=color)

def draw_sub_page(draw, title):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.text((15, 20), title, font=font, fill=WHITE)
    draw.text((15, 80), "test", font=small_font, fill=WHITE)
    draw.text((15, 100), "Exit", font=small_font, fill=BLUE if selected_index == 0 else WHITE)

def draw_jamming_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    if jamming_active:
        draw.text((15, 30), "Jamming Active", font=font, fill=BLUE)
        draw.text((15, 80), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    else:
        draw.text((15, 50), "Start", font=font, fill=BLUE if selected_index == 0 else WHITE)
        draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

def draw_capture_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    if capture_active:
        draw.text((15, 30), f"Capturing {capture_bit}", font=font, fill=BLUE)
        draw.text((15, 80), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    else:
        draw_menu(draw, capture_menu, selected_index)

def draw_wifi_test_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.text((15, 50), "Test Wifi", font=font, fill=BLUE if selected_index == 0 else WHITE)
    draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

# Main loop
running = True
while running:
    # Read joystick inputs
    vrx = read_adc(0)
    vry = read_adc(1)
    button_state = GPIO.input(16)

    # Handle joystick movement
    current_time = time.time()
    if current_time - last_move_time > move_delay:
        if vry < 10000:
            selected_index = max(0, selected_index - 1)
            last_move_time = current_time
        elif vry > 60000:
            if current_menu == "main":
                selected_index = min(len(main_menu) - 1, selected_index + 1)
            elif current_menu == "security":
                selected_index = min(len(security_menu) - 1, selected_index + 1)
            elif current_menu == "attack":
                selected_index = min(len(attack_menu) - 1, selected_index + 1)
            elif current_menu == "capture":
                selected_index = min(len(capture_menu) - 1, selected_index + 1)
            elif current_menu in ["jamming", "wifi"]:
                selected_index = min(1, selected_index + 1)
            elif current_menu in ["info", "security_sub", "attack_sub"]:
                selected_index = 0
            last_move_time = current_time

    # Handle button press
    if button_state == False and last_button_state == True:
        if current_menu == "main":
            if selected_index == 0:
                current_menu = "info"
                selected_index = 0
            elif selected_index == 1:
                current_menu = "security"
                selected_index = 0
            elif selected_index == 2:
                current_menu = "attack"
                selected_index = 0
            elif selected_index == 3:
                current_menu = "wifi"
                selected_index = 0
        elif current_menu == "security":
            if selected_index == len(security_menu) - 1:
                current_menu = "main"
                selected_index = 1
            elif selected_index == 1:  # Captcher My RF kye
                current_menu = "capture"
                selected_index = 0
            else:
                current_menu = "security_sub"
                current_page = security_menu[selected_index]
                selected_index = 0
        elif current_menu == "attack":
            if selected_index == len(attack_menu) - 1:
                current_menu = "main"
                selected_index = 2
            elif selected_index == 0:  # Jamming
                current_menu = "jamming"
                selected_index = 0
            elif selected_index == 1:  # Captcher RF kye
                current_menu = "capture"
                selected_index = 0
            else:
                current_menu = "attack_sub"
                current_page = attack_menu[selected_index]
                selected_index = 0
        elif current_menu == "jamming":
            if selected_index == 0:
                if jamming_active:
                    if jamming_process:
                        try:
                            jamming_process.send_signal(signal.SIGINT)
                            jamming_process.wait(timeout=5)
                            print("✅ Jamming stopped.")
                        except Exception as e:
                            print(f"⚠️ Error stopping Jamming.py: {e}")
                        jamming_process = None
                        jamming_active = False
                else:
                    try:
                        jamming_process = subprocess.Popen(["python3", "/home/pi/Jamming.py"])
                        jamming_active = True
                        print("🚨 Jamming started.")
                    except Exception as e:
                        print(f"⚠️ Error starting Jamming.py: {e}")
            elif selected_index == 1:
                if jamming_active and jamming_process:
                    try:
                        jamming_process.send_signal(signal.SIGINT)
                        jamming_process.wait(timeout=5)
                        print("✅ Jamming stopped.")
                    except Exception as e:
                        print(f"⚠️ Error stopping Jamming.py: {e}")
                    jamming_process = None
                    jamming_active = False
                current_menu = "attack"
                selected_index = 0
        elif current_menu == "capture":
            if selected_index == len(capture_menu) - 1:  # Exit
                current_menu = "security" if current_page == "Captcher My RF kye" else "attack"
                selected_index = 1
                capture_bit = None
            elif capture_active:
                if selected_index == 0:  # Stop
                    if capture_process:
                        try:
                            capture_process.send_signal(signal.SIGINT)
                            capture_process.wait(timeout=5)
                            print(f"✅ Capturing {capture_bit} stopped.")
                        except Exception as e:
                            print(f"⚠️ Error stopping recever{capture_bit.lower()}.py: {e}")
                        capture_process = None
                        capture_active = False
                        capture_bit = None
            else:
                if selected_index in [0, 1, 2, 3]:  # 24BIT, 32BIT, 64BIT, 128BIT
                    bit_options = ["24", "32", "64", "128"]
                    capture_bit = bit_options[selected_index]
                    try:
                        capture_process = subprocess.Popen(["python3", f"/home/pi/recever{capture_bit}.py"])
                        capture_active = True
                        print(f"🚨 Capturing {capture_bit} started.")
                    except Exception as e:
                        print(f"⚠️ Error starting recever{capture_bit}.py: {e}")
        elif current_menu == "wifi":
            if selected_index == 1:
                current_menu = "main"
                selected_index = 3
        elif current_menu in ["info", "security_sub", "attack_sub"]:
            if selected_index == 0:
                if current_menu == "info":
                    current_menu = "main"
                    selected_index = 0
                elif current_menu == "security_sub":
                    current_menu = "security"
                    selected_index = 0
                elif current_menu == "attack_sub":
                    current_menu = "attack"
                    selected_index = 0

    last_button_state = button_state

    # Render current page
    with canvas(device) as draw:
        if current_menu == "main":
            draw_menu(draw, main_menu, selected_index)
        elif current_menu == "security":
            draw_menu(draw, security_menu, selected_index)
        elif current_menu == "attack":
            draw_menu(draw, attack_menu, selected_index)
        elif current_menu == "info":
            draw_info_page(draw)
        elif current_menu == "jamming":
            draw_jamming_page(draw)
        elif current_menu == "capture":
            draw_capture_page(draw)
        elif current_menu == "security_sub" or current_menu == "attack_sub":
            draw_sub_page(draw, current_page)
        elif current_menu == "wifi":
            draw_wifi_test_page(draw)

    time.sleep(0.01)

# Cleanup
if jamming_active and jamming_process:
    try:
        jamming_process.send_signal(signal.SIGINT)
        jamming_process.wait(timeout=5)
        print("✅ Jamming stopped during cleanup.")
    except Exception as e:
        print(f"⚠️ Error during jamming cleanup: {e}")
if capture_active and capture_process:
    try:
        capture_process.send_signal(signal.SIGINT)
        capture_process.wait(timeout=5)
        print(f"✅ Capturing {capture_bit} stopped during cleanup.")
    except Exception as e:
        print(f"⚠️ Error during capture cleanup: {e}")
GPIO.cleanup()
device.cleanup()
