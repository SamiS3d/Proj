import time
import smbus2
import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from luma.core.render import canvas
from PIL import Image, ImageDraw, ImageFont

# Initialize ST7735 display
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_CS=8)
device = st7735(serial, width=128, height=128, rotate=1)  # 90° clockwise
device.backlight(True)  # Turn on backlight (assumes GPIO 18)

# GPIO and I2C setup for joystick
GPIO.setmode(GPIO.BCM)
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Joystick button
bus = smbus2.SMBus(1)  # I2C bus for ADS1115
ADS1115_ADDRESS = 0x48

# ADS1115 configuration
def read_adc(channel):
    try:
        # Configure for single-ended reading on specified channel
        config = 0xC183 | (channel << 12)  # Single-ended, ±4.096V range
        bus.write_i2c_block_data(ADS1115_ADDRESS, 0x01, [(config >> 8) & 0xFF, config & 0xFF])
        time.sleep(0.01)  # Wait for conversion
        data = bus.read_i2c_block_data(ADS1115_ADDRESS, 0x00, 2)
        value = (data[0] << 8) | data[1]
        print(f"Channel {channel}: {value}")  # Debug per channel
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
security_menu = ["Jamming Detection", "Captcher My RF kye", "Captcher My RF kye Rolling", "Reuse My RF kye", "Exit"]  # Added Exit
attack_menu = ["Jamming", "Captcher RF kye", "Captcher RF kye Rolling", "Reuse My RF kye", "Exit"]   # Added Exit

# State variables
current_menu = "main"
selected_index = 0
current_page = None
last_button_state = True
last_move_time = 0
move_delay = 0.2  # Debounce delay

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

def draw_wifi_test_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.text((15, 50), "Start", font=font, fill=BLUE if selected_index == 0 else WHITE)
    draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

# Main loop
running = True
while running:
    # Read joystick inputs
    vrx = read_adc(0)  # X-axis (unused)
    vry = read_adc(1)  # Y-axis
    button_state = GPIO.input(16)  # Button (active low)

    # Handle joystick movement
    current_time = time.time()
    if current_time - last_move_time > move_delay:
        if vry < 10000:  # Up (~3341)
            selected_index = max(0, selected_index - 1)
            last_move_time = current_time
        elif vry > 60000:  # Down (~61680)
            if current_menu == "main":
                selected_index = min(len(main_menu) - 1, selected_index + 1)
            elif current_menu == "security":
                selected_index = min(len(security_menu) - 1, selected_index + 1)
            elif current_menu == "attack":
                selected_index = min(len(attack_menu) - 1, selected_index + 1)
            elif current_menu == "wifi":
                selected_index = min(1, selected_index + 1)
            elif current_menu in ["info", "security_sub", "attack_sub"]:
                selected_index = 0  # Only Exit is selectable
            last_move_time = current_time

    # Handle button press
    if button_state == False and last_button_state == True:  # Button pressed
        if current_menu == "main":
            if selected_index == 0:  # Info
                current_menu = "info"
                selected_index = 0
            elif selected_index == 1:  # Security part
                current_menu = "security"
                selected_index = 0
            elif selected_index == 2:  # Attack part
                current_menu = "attack"
                selected_index = 0
            elif selected_index == 3:  # Wifi Test
                current_menu = "wifi"
                selected_index = 0
        elif current_menu == "security":
            if selected_index == len(security_menu) - 1:  # Exit
                current_menu = "main"
                selected_index = 1
            else:
                current_menu = "security_sub"
                current_page = security_menu[selected_index]
                selected_index = 0
        elif current_menu == "attack":
            if selected_index == len(attack_menu) - 1:  # Exit
                current_menu = "main"
                selected_index = 2
            else:
                current_menu = "attack_sub"
                current_page = attack_menu[selected_index]
                selected_index = 0
        elif current_menu == "wifi":
            if selected_index == 0:
                pass  # Start action (placeholder)
            elif selected_index == 1:
                current_menu = "main"
                selected_index = 3
        elif current_menu in ["info", "security_sub", "attack_sub"]:
            if selected_index == 0:  # Exit
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
        elif current_menu == "security_sub" or current_menu == "attack_sub":
            draw_sub_page(draw, current_page)
        elif current_menu == "wifi":
            draw_wifi_test_page(draw)

    time.sleep(0.01)  # Prevent CPU overload

GPIO.cleanup()
device.cleanup()
