from luma.core.render import canvas
from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from PIL import Image, ImageDraw, ImageFont
import time
import smbus2
import RPi.GPIO as GPIO
import subprocess
import signal
import os
from rpi_rf import RFDevice
import threading
import queue
import psutil

# تحديد المسار الأساسي
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# وظيفة لحفظ الرموز في ملف
def save_key(key):
    # Save new key directly without checking for duplicates
    count = get_saved_keys_count() + 1
    kar_name = f"kar{count}"
    with open(os.path.join(BASE_DIR, "keys.txt"), "a") as f:
        f.write(f"{kar_name}:{key}\n")
    print(f"✅ Saved new key as {kar_name}: {key}")
    return kar_name

# وظيفة لقراءة عدد الرموز المحفوظة
def get_saved_keys_count():
    try:
        with open(os.path.join(BASE_DIR, "keys.txt"), "r") as f:
            return len(f.readlines())
    except FileNotFoundError:
        return 0

# وظيفة لقراءة الرموز المحفوظة
def get_saved_keys():
    try:
        with open(os.path.join(BASE_DIR, "keys.txt"), "r") as f:
            keys = [line.strip().split(":", 1) for line in f.readlines() if ":" in line]
            print(f"🔍 Read keys: {keys}")
            return keys if keys else []
    except FileNotFoundError:
        print("⚠️ keys.txt not found")
        return []
    except Exception as e:
        print(f"⚠️ Error reading keys.txt: {e}")
        return []

# وظيفة حذف رمز من ملف keys.txt
def delete_key(kar_name):
    try:
        keys = get_saved_keys()
        keys = [key for key in keys if key[0] != kar_name]
        with open(os.path.join(BASE_DIR, "keys.txt"), "w") as f:
            for kar_name, key_val in keys:
                f.write(f"{kar_name}:{key_val}\n")
        print(f"🗑️ Deleted key: {kar_name}")
    except Exception as e:
        print(f"⚠️ Error deleting key: {e}")

# وظيفة إرسال الرمز باستخدام rpi_rf
def send_rf_key(code):
    GPIO_PIN = 20
    try:
        if not GPIO.getmode():
            GPIO.setmode(GPIO.BCM)
            print("🔧 Re-initialized GPIO mode to BCM")
        GPIO.setup(GPIO_PIN, GPIO.OUT)
        rfdevice = RFDevice(GPIO_PIN)
        rfdevice.enable_tx()
        print(f"📤 Sending code: {code}")
        rfdevice.tx_code(int(code))
        print("✅ Done sending.")
        GPIO.cleanup(GPIO_PIN)
        print("🧹 Cleaned up GPIO pin 20")
    except Exception as e:
        print(f"⚠️ Error sending code: {e}")
    finally:
        try:
            GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(24, GPIO.OUT)  # DC
            GPIO.setup(25, GPIO.OUT)  # RST
            GPIO.setup(8, GPIO.OUT)   # CS
            print("🔧 Re-initialized GPIO pins for joystick and display")
        except Exception as e:
            print(f"⚠️ Error re-initializing GPIO pins: {e}")

# وظيفة إعادة تهيئة الشاشة
def reinitialize_display():
    global device
    try:
        serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_CS=8)
        device = st7735(serial, width=128, height=128, rotate=1)
        device.backlight(True)
        print("🖥️ Re-initialized display")
    except Exception as e:
        print(f"⚠️ Error re-initializing display: {e}")

# وظيفة إيقاف جميع العمليات
def stop_all_processes():
    global jamming_process, jamming_active
    global jamming_detect_process, jamming_detect_active
    global capture_process, capture_active, capture_bit, recent_outputs

    # إيقاف Jamming
    if jamming_active and jamming_process:
        try:
            jamming_process.send_signal(signal.SIGINT)
            jamming_process.wait(timeout=5)
            print("✅ Jamming stopped (auto).")
        except Exception as e:
            print(f"⚠️ Error stopping Jamming.py: {e}")
        jamming_process = None
        jamming_active = False

    # إيقاف Jamming Detection
    if jamming_detect_active and jamming_detect_process:
        try:
            jamming_detect_process.send_signal(signal.SIGINT)
            jamming_detect_process.wait(timeout=5)
            print("✅ Jamming Detection stopped (auto).")
        except Exception as e:
            print(f"⚠️ Error stopping Jammingdetect.py: {e}")
        jamming_detect_process = None
        jamming_detect_active = False
        recent_outputs = []

    # إيقاف Capture
    if capture_active and capture_process:
        try:
            capture_process.send_signal(signal.SIGINT)
            capture_process.wait(timeout=5)
            print(f"✅ Capture {capture_bit} stopped (auto).")
        except Exception as e:
            print(f"⚠️ Error stopping capture: {e}")
        capture_process = None
        capture_active = False
        capture_bit = None
        recent_outputs = []

    # تنظيف أي عمليات متبقية
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if 'python3' in proc.info['name'] and any(
                x in proc.cmdline() for x in ['recever24.py', 'recever32.py', 'recever64.py', 'recever128.py']
            ):
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=5)
                print(f"🧹 Terminated stray receiver process: {proc.info['name']}")
    except Exception as e:
        print(f"⚠️ Error terminating stray processes: {e}")

    # إعادة تشغيل pigpiod لو معلّق
    try:
        subprocess.run(["sudo", "pkill", "pigpiod"], check=True)
        time.sleep(0.5)
        subprocess.run(["sudo", "pigpiod"], check=True)
        print("🔄 Restarted pigpiod daemon")
    except Exception as e:
        print(f"⚠️ Error restarting pigpiod: {e}")

    # تنظيف الـ GPIO
    try:
        GPIO.cleanup([20, 16, 24, 25, 8])
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(24, GPIO.OUT)
        GPIO.setup(25, GPIO.OUT)
        GPIO.setup(8, GPIO.OUT)
        print("🧹 Cleaned and re-initialized GPIO pins")
    except Exception as e:
        print(f"⚠️ Error cleaning GPIO: {e}")

# تهيئة الشاشة ST7735
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_CS=8)
device = st7735(serial, width=128, height=128, rotate=1)
device.backlight(True)

# إعداد GPIO و I2C للجويستيك
GPIO.setmode(GPIO.BCM)
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
bus = smbus2.SMBus(1)
ADS1115_ADDRESS = 0x48

def read_adc(channel):
    try:
        config = 0xC183 | (channel << 12)
        bus.write_i2c_block_data(ADS1115_ADDRESS, 0x01, [(config >> 8) & 0xFF, config & 0xFF])
        time.sleep(0.01)
        data = bus.read_i2c_block_data(ADS1115_ADDRESS, 0x00, 2)
        return (data[0] << 8) | data[1]
    except Exception as e:
        return 0

# الألوان
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 120, 255)
GRAY = (50, 50, 50)
DARK_GRAY = (30, 30, 30)
LIGHT_BLUE = (100, 180, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

# الخطوط
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    tiny_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
except IOError:
    font = ImageFont.load_default()
    small_font = ImageFont.load_default()
    tiny_font = ImageFont.load_default()

# هيكلية القوائم
main_menu = ["Info", "Security part", "Attack part", "Wifi Test", "Poweroff"]
security_menu = ["Jamming Detection", "Captcher My RF kye", "Captcher My RF kye Rolling", "Reuse My RF kye", "Exit"]
attack_menu = ["Jamming", "Captcher RF kye", "Captcher RF kye Rolling", "Reuse My RF kye", "Exit"]
capture_menu = ["24BIT", "32BIT", "64BIT", "128BIT", "Exit"]
key_action_menu = ["Send", "Delete", "Exit"]

# متغيرات الحالة
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
jamming_detect_process = None
jamming_detect_active = False
capture_output = queue.Queue()
recent_outputs = []
selecting_key = False
previous_menu = None
selected_key = None

# وظيفة لقراءة مخرجات العملية
def read_process_output(process, output_queue):
    try:
        while process.poll() is None:
            line = process.stdout.readline()
            if line:
                output_queue.put(line.strip())
    except Exception as e:
        print(f"⚠️ Error reading process output: {e}")

# رسم القوائم
def draw_menu(draw, items, selected):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    # Draw header
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), "Menu", font=font, fill=WHITE)
    
    # عدد العناصر المعروضة في الشاشة (Viewport)
    max_display_items = 4
    # حساب أول عنصر يتم عرضه بناءً على المؤشر
    if len(items) <= max_display_items:
        start_index = 0
    else:
        start_index = max(0, min(selected - 1, len(items) - max_display_items))
    
    # عرض العناصر ضمن نافذة العرض
    for i in range(start_index, min(start_index + max_display_items, len(items))):
        y = 25 + (i - start_index) * 22
        if i == selected:
            draw.rounded_rectangle((5, y, 122, y + 20), radius=5, fill=LIGHT_BLUE)
            draw.text((15, y + 3), items[i], font=small_font, fill=BLACK)
            # Draw selection icon
            draw.polygon([(8, y + 8), (12, y + 12), (8, y + 16)], fill=BLACK)
        else:
            draw.rounded_rectangle((5, y, 122, y + 20), radius=5, fill=GRAY)
            draw.text((15, y + 3), items[i], font=small_font, fill=WHITE)
def draw_info_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), "Project Info", font=font, fill=WHITE)
    lines = [
        "Graduation Project",
        "Cybersecurity",
        "Requirement",
        "By: Sami Saad",
        "Ahmed Rashid",
        "Exit"
    ]
    for i, line in enumerate(lines):
        y = 25 + i * 18
        if i == len(lines) - 1 and selected_index == 0:
            draw.rounded_rectangle((5, y, 122, y + 16), radius=5, fill=LIGHT_BLUE)
            draw.text((15, y + 2), line, font=small_font, fill=BLACK)
            draw.polygon((8, y + 6, 12, y + 10, 8, y + 14), fill=BLACK)
        else:
            draw.text((10, y + 2), line, font=small_font, fill=WHITE)

def draw_sub_page(draw, title):
    global recent_outputs, selecting_key
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), title, font=font, fill=WHITE)
    
    if title == "Jamming Detection" and jamming_detect_active:
        try:
            while not capture_output.empty():
                line = capture_output.get_nowait()
                recent_outputs.append(line)
                if len(recent_outputs) > 3:
                    recent_outputs.pop(0)
            for i, output in enumerate(recent_outputs):
                draw.rounded_rectangle((5, 30 + i * 15, 122, 45 + i * 15), radius=3, fill=GRAY)
                draw.text((10, 32 + i * 15), output[:20], font=tiny_font, fill=WHITE)
            if selected_index == 0:
                draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=RED)
                draw.text((10, 102), "Stop", font=small_font, fill=BLACK)
            else:
                draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=GRAY)
                draw.text((10, 102), "Stop", font=small_font, fill=WHITE)
        except queue.Empty:
            for i, output in enumerate(recent_outputs):
                draw.rounded_rectangle((5, 30 + i * 15, 122, 45 + i * 15), radius=3, fill=GRAY)
                draw.text((10, 32 + i * 15), output[:20], font=tiny_font, fill=WHITE)
            if selected_index == 0:
                draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=RED)
                draw.text((10, 102), "Stop", font=small_font, fill=BLACK)
            else:
                draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=GRAY)
                draw.text((10, 102), "Stop", font=small_font, fill=WHITE)
    elif title in ["Captcher My RF kye", "Captcher RF kye"] and selecting_key:
        saved_keys = get_saved_keys()
        for i, (kar_name, key) in enumerate(saved_keys):
            y = 30 + i * 15
            if i == selected_index:
                draw.rounded_rectangle((5, y, 122, y + 14), radius=3, fill=LIGHT_BLUE)
                draw.text((15, y + 2), f"{kar_name}: {key[:10]}...", font=tiny_font, fill=BLACK)
                draw.polygon((8, y + 5, 12, y + 9, 8, y + 13), fill=BLACK)
            else:
                draw.rounded_rectangle((5, y, 122, y + 14), radius=3, fill=GRAY)
                draw.text((15, y + 2), f"{kar_name}: {key[:10]}...", font=tiny_font, fill=WHITE)
        select_y = 90 + len(saved_keys) * 15
        if selected_index == len(saved_keys):
            draw.rounded_rectangle((5, select_y, 60, select_y + 14), radius=5, fill=LIGHT_BLUE)
            draw.text((10, select_y + 2), "Select", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((5, select_y, 60, select_y + 14), radius=5, fill=GRAY)
            draw.text((10, select_y + 2), "Select", font=small_font, fill=WHITE)
        if selected_index == len(saved_keys) + 1:
            draw.rounded_rectangle((65, select_y, 122, select_y + 14), radius=5, fill=RED)
            draw.text((70, select_y + 2), "Exit", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((65, select_y, 122, select_y + 14), radius=5, fill=GRAY)
            draw.text((70, select_y + 2), "Exit", font=small_font, fill=WHITE)
    elif title == "Reuse My RF kye":
        saved_keys = get_saved_keys()
        if not saved_keys:
            draw.text((10, 40), "No keys saved", font=small_font, fill=WHITE)
            if selected_index == 0:
                draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=RED)
                draw.text((10, 102), "Exit", font=small_font, fill=BLACK)
            else:
                draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=GRAY)
                draw.text((10, 102), "Exit", font=small_font, fill=WHITE)
        else:
            # عدد العناصر المعروضة في الشاشة (Viewport)
            max_display_items = 4
            # حساب أول عنصر يتم عرضه بناءً على المؤشر
            if len(saved_keys) <= max_display_items:
                start_index = 0
            else:
                start_index = max(0, min(selected_index - 1, len(saved_keys) - max_display_items))
            
            # عرض المفاتيح ضمن نافذة العرض
            for i in range(start_index, min(start_index + max_display_items, len(saved_keys))):
                y = 30 + (i - start_index) * 15
                if i == selected_index:
                    draw.rounded_rectangle((5, y, 122, y + 14), radius=3, fill=LIGHT_BLUE)
                    draw.text((15, y + 2), f"{saved_keys[i][0]}: {saved_keys[i][1][:10]}...", font=tiny_font, fill=BLACK)
                    draw.polygon((8, y + 5, 12, y + 9, 8, y + 13), fill=BLACK)
                else:
                    draw.rounded_rectangle((5, y, 122, y + 14), radius=3, fill=GRAY)
                    draw.text((15, y + 2), f"{saved_keys[i][0]}: {saved_keys[i][1][:10]}...", font=tiny_font, fill=WHITE)
            
            # عرض أزرار Select و Exit
            select_y = 30 + min(len(saved_keys), max_display_items) * 15
            if selected_index == len(saved_keys):
                draw.rounded_rectangle((5, select_y, 60, select_y + 14), radius=5, fill=LIGHT_BLUE)
                draw.text((10, select_y + 2), "Select", font=small_font, fill=BLACK)
            else:
                draw.rounded_rectangle((5, select_y, 60, select_y + 14), radius=5, fill=GRAY)
                draw.text((10, select_y + 2), "Select", font=small_font, fill=WHITE)
            if selected_index == len(saved_keys) + 1:
                draw.rounded_rectangle((65, select_y, 122, select_y + 14), radius=5, fill=RED)
                draw.text((70, select_y + 2), "Exit", font=small_font, fill=BLACK)
            else:
                draw.rounded_rectangle((65, select_y, 122, select_y + 14), radius=5, fill=GRAY)
                draw.text((70, select_y + 2), "Exit", font=small_font, fill=WHITE)
    else:
        if selected_index == 0:
            draw.rounded_rectangle((5, 80, 60, 96), radius=5, fill=GREEN)
            draw.text((10, 82), "Start" if title == "Jamming Detection" else "Test", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((5, 80, 60, 96), radius=5, fill=GRAY)
            draw.text((10, 82), "Start" if title == "Jamming Detection" else "Test", font=small_font, fill=WHITE)
        if selected_index == 0:
            draw.rounded_rectangle((65, 80, 122, 96), radius=5, fill=RED)
            draw.text((70, 82), "Exit", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((65, 80, 122, 96), radius=5, fill=GRAY)
            draw.text((70, 82), "Exit", font=small_font, fill=WHITE)

def draw_jamming_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), "Jamming", font=font, fill=WHITE)
    if jamming_active:
        draw.text((10, 40), "Jamming Active", font=font, fill=LIGHT_BLUE)
        draw.ellipse((90, 35, 100, 45), fill=GREEN)  # Active indicator
        if selected_index == 0:
            draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=RED)
            draw.text((10, 102), "Stop", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=GRAY)
            draw.text((10, 102), "Stop", font=small_font, fill=WHITE)
    else:
        if selected_index == 0:
            draw.rounded_rectangle((5, 50, 60, 66), radius=5, fill=GREEN)
            draw.text((10, 52), "Start", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((5, 50, 60, 66), radius=5, fill=GRAY)
            draw.text((10, 52), "Start", font=small_font, fill=WHITE)
        if selected_index == 1:
            draw.rounded_rectangle((65, 50, 122, 66), radius=5, fill=RED)
            draw.text((70, 52), "Exit", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((65, 50, 122, 66), radius=5, fill=GRAY)
            draw.text((70, 52), "Exit", font=small_font, fill=WHITE)

def draw_capture_page(draw):
    global recent_outputs
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), "Capture RF", font=font, fill=WHITE)
    if capture_active:
        draw.text((10, 30), f"Capturing {capture_bit}", font=small_font, fill=LIGHT_BLUE)
        draw.ellipse((90, 25, 100, 35), fill=GREEN)  # Active indicator
        try:
            while not capture_output.empty():
                line = capture_output.get_nowait()
                recent_outputs.append(line)
                if len(recent_outputs) > 3:
                    recent_outputs.pop(0)
        except queue.Empty:
            pass
        for i, output in enumerate(recent_outputs):
            draw.rounded_rectangle((5, 50 + i * 15, 122, 65 + i * 15), radius=3, fill=GRAY)
            draw.text((10, 52 + i * 15), output[:20], font=tiny_font, fill=WHITE)
        if selected_index == 0:
            draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=RED)
            draw.text((10, 102), "Stop", font=small_font, fill=BLACK)
        else:
            draw.rounded_rectangle((5, 100, 60, 116), radius=5, fill=GRAY)
            draw.text((10, 102), "Stop", font=small_font, fill=WHITE)
    else:
        draw_menu(draw, capture_menu, selected_index)

def draw_wifi_test_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), "Wifi Test", font=font, fill=WHITE)
    if selected_index == 0:
        draw.rounded_rectangle((5, 50, 60, 66), radius=5, fill=GREEN)
        draw.text((10, 52), "Test Wifi", font=small_font, fill=BLACK)
    else:
        draw.rounded_rectangle((5, 50, 60, 66), radius=5, fill=GRAY)
        draw.text((10, 52), "Test Wifi", font=small_font, fill=WHITE)
    if selected_index == 1:
        draw.rounded_rectangle((65, 50, 122, 66), radius=5, fill=RED)
        draw.text((70, 52), "Exit", font=small_font, fill=BLACK)
    else:
        draw.rounded_rectangle((65, 50, 122, 66), radius=5, fill=GRAY)
        draw.text((70, 52), "Exit", font=small_font, fill=WHITE)

def draw_key_action_page(draw, kar_name, key_val):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
    draw.text((5, 3), "Key Actions", font=font, fill=WHITE)
    draw.rounded_rectangle((5, 30, 122, 60), radius=5, fill=GRAY)
    draw.text((10, 32), f"Key: {kar_name}", font=small_font, fill=WHITE)
    draw.text((10, 47), f"Val: {key_val[:10]}...", font=tiny_font, fill=WHITE)
    for i, item in enumerate(key_action_menu):
        y = 70 + i * 18
        if i == selected_index:
            draw.text((15, y + 2), item, font=small_font, fill=BLACK)
            draw.polygon((8, y + 6, 12, y + 10, 8, y + 14), fill=BLACK)
        else:
            draw.rounded_rectangle((5, y, 122, y + 16), radius=5, fill=GRAY)
            draw.text((15, y + 2), item, font=small_font, fill=WHITE)

# الحلقة الرئيسية
running = True
while running:
    try:
        if not GPIO.getmode():
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(24, GPIO.OUT)
            GPIO.setup(25, GPIO.OUT)
            GPIO.setup(8, GPIO.OUT)
            print("🔍🔍 Re-initialized GPIO mode and pins")
        
        vrx = read_adc(0)
        vry = read_adc(1)
        button_state = GPIO.input(16)
    except Exception as e:
        print(f"⚠️ GPIO Error: {e}")
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(24, GPIO.OUT)
            draw.text((10, 20), "Error", font=small_font, fill=WHITE)
            GPIO.setup(8, GPIO.OUT)
            print("🔍🔍 Re-initialized GPIO pins")
            button_state = True
        except Exception as e:
            print(f"⚠️ Error re-initializing GPIO: {e}")
            button_state = True
        vrx, vry = 0, 0

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
            elif current_menu == "jamming" or current_menu == "wifi":
                selected_index = min(1, selected_index + 1)
            elif current_menu in ["security_sub", "attack_sub"] and current_page in ["Captcher My RF kye", "Captcher RF kye"] and selecting_key:
                saved_keys = get_saved_keys()
                selected_index = min(len(saved_keys) + 1, selected_index + 1)
            elif current_menu in ["security_sub", "attack_sub"] and current_page == "Reuse My RF kye":
                saved_keys = get_saved_keys()
                selected_index = min(len(saved_keys) + 1, selected_index + 1)
            elif current_menu == "key_action":
                selected_index = min(len(key_action_menu) - 1, selected_index + 1)
            last_move_time = current_time

    if button_state == False and last_button_state == True:
        print(f"🔄 Current menu: {current_menu}, selected_index: {selected_index}")
        if current_menu == "main":
            if selected_index == 0:
                current_menu = "info"
                selected_index = 0
            elif selected_index == 1:
                current_menu = "security"
                previous_menu = "security"
                selected_index = 0
            elif selected_index == 2:
                current_menu = "attack"
                previous_menu = "attack"
                selected_index = 0
            elif selected_index == 3:
                current_menu = "wifi"
                selected_index = 0
            elif selected_index == 4:  # Poweroff
                print("🔌 Initiating system poweroff")
                # Display shutdown message
                try:
                    with canvas(device) as draw:
                        draw.rectangle((0, 0, 127, 127), fill=BLACK)
                        draw.rectangle((0, 0, 127, 20), fill=DARK_GRAY)
                        draw.text((5, 3), "Poweroff", font=font, fill=WHITE)
                        draw.text((10, 50), "Shutting down...", font=small_font, fill=RED)
                    time.sleep(2)  # Show message for 2 seconds
                except Exception as e:
                    print(f"⚠️ Error displaying shutdown message: {e}")
                # Stop processes and cleanup
                stop_all_processes()
                try:
                    device.backlight(False)  # Turn off backlight
                    device.hide()  # Turn off display
                except Exception as e:
                    print(f"⚠️ Error during display cleanup: {e}")
                try:
                    GPIO.cleanup([16, 24, 25, 8])  # Clean GPIO pins
                except Exception as e:
                    print(f"⚠️ Error during GPIO cleanup: {e}")
                try:
                    subprocess.run(["sudo", "poweroff"], check=True)
                except Exception as e:
                    print(f"⚠️ Error executing poweroff: {e}")
                running = False
        elif current_menu == "security":
            if selected_index == len(security_menu) - 1:
                current_menu = "main"
                selected_index = 1
            elif selected_index == 0:
                current_menu = "security_sub"
                current_page = security_menu[selected_index]
                selected_index = 0
                if jamming_detect_active:
                    if jamming_detect_process:
                        try:
                            jamming_detect_process.send_signal(signal.SIGINT)
                            jamming_detect_process.wait(timeout=5)
                            print("✅ Jamming Detection stopped.")
                        except Exception as e:
                            print(f"⚠️ Error stopping Jammingdetect.py: {e}")
                        jamming_detect_process = None
                        jamming_detect_active = False
                        recent_outputs = []
                else:
                    try:
                        stop_all_processes()
                        jamming_detect_process = subprocess.Popen(
                            ["python3", os.path.join(BASE_DIR, "Jammingdetect.py")],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                        threading.Thread(target=read_process_output, args=(jamming_detect_process, capture_output), daemon=True).start()
                        jamming_detect_active = True
                        print("🚨 Jamming Detection started.")
                    except Exception as e:
                        print(f"⚠️ Error starting Jammingdetect.py: {e}")
            elif selected_index == 1:
                current_menu = "capture"
                previous_menu = "security"
                selected_index = 0
                recent_outputs = []
            elif selected_index == 3:
                print("🔄 Entering Reuse My RF kye (security)")
                current_menu = "security_sub"
                current_page = security_menu[selected_index]
                saved_keys = get_saved_keys()
                selected_index = 0
            else:
                current_menu = "security_sub"
                current_page = security_menu[selected_index]
                selected_index = 0
        elif current_menu == "attack":
            if selected_index == len(attack_menu) - 1:
                current_menu = "main"
                selected_index = 2
            elif selected_index == 0:
                current_menu = "jamming"
                selected_index = 0
            elif selected_index == 1:
                current_menu = "capture"
                previous_menu = "attack"
                selected_index = 0
                recent_outputs = []
            elif selected_index == 3:
                print("🔄 Entering Reuse My RF kye (attack)")
                current_menu = "attack_sub"
                current_page = attack_menu[selected_index]
                saved_keys = get_saved_keys()
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
                        stop_all_processes()
                        jamming_process = subprocess.Popen(
                            ["python3", os.path.join(BASE_DIR, "Jamming.py")],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
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
                if capture_active and capture_process:
                    try:
                        capture_process.send_signal(signal.SIGINT)
                        capture_process.wait(timeout=5)
                        print(f"✅ Capturing {capture_bit} stopped.")
                    except Exception as e:
                        print(f"⚠️ Error stopping recever{capture_bit.lower()}.py: {e}")
                    capture_process = None
                    capture_active = False
                    capture_bit = None
                    recent_outputs = []
                stop_all_processes()
                current_menu = previous_menu
                selected_index = 1
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
                        recent_outputs = []
                    stop_all_processes()
            else:
                if selected_index in [0, 1, 2, 3]:  # Start capture
                    bit_options = ["24", "32", "64", "128"]
                    capture_bit = bit_options[selected_index]
                    stop_all_processes()
                    try:
                        capture_output = queue.Queue()
                        capture_process = subprocess.Popen(
                            ["python3", os.path.join(BASE_DIR, f"recever{capture_bit}.py")],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                        threading.Thread(target=read_process_output, args=(capture_process, capture_output), daemon=True).start()
                        capture_active = True
                        print(f"🚨 Capturing {capture_bit} started.")
                    except Exception as e:
                        print(f"⚠️ Error starting recever{capture_bit}.py: {e}")
                        capture_process = None
                        capture_active = False
                        capture_bit = None
                        stop_all_processes()
        elif current_menu in ["security_sub", "attack_sub"] and current_page in ["Captcher My RF kye", "Captcher RF kye"] and selecting_key:
            saved_keys = get_saved_keys()
            if selected_index < len(saved_keys):
                key = saved_keys[selected_index][1]
                key_name = save_key(key)
                print(f"✅ Key selected: {key_name}: {key}")
            elif selected_index == len(saved_keys) + 1:
                selecting_key = False
                current_menu = previous_menu
                selected_index = 1
        elif current_menu in ["security_sub", "attack_sub"] and current_page == "Reuse My RF kye":
            saved_keys = get_saved_keys()
            if selected_index < len(saved_keys):
                selected_key = saved_keys[selected_index]
                current_menu = "key_action"
                selected_index = 0
            elif selected_index == len(saved_keys) + 1:
                current_menu = previous_menu
                selected_index = 3
        elif current_menu == "key_action":
            if selected_index == 0:  # Send
                if selected_key:
                    send_rf_key(selected_key[1])
                current_menu = "security_sub" if previous_menu == "security" else "attack_sub"
                current_page = "Reuse My RF kye"
                selected_index = 0
            elif selected_index == 1:  # Delete
                if selected_key:
                    delete_key(selected_key[0])
                current_menu = "security_sub" if previous_menu == "security" else "attack_sub"
                current_page = "Reuse My RF kye"
                selected_index = 0
            elif selected_index == 2:  # Exit
                current_menu = previous_menu
                current_page = None
                selected_index = 3
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

    try:
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
            elif current_menu in ["security_sub", "attack_sub"]:
                draw_sub_page(draw, current_page)
            elif current_menu == "wifi":
                draw_wifi_test_page(draw)
            elif current_menu == "key_action":
                draw_key_action_page(draw, selected_key[0], selected_key[1])
    except Exception as e:
        print(f"⚠️ Error drawing: {e}")
        reinitialize_display()

    time.sleep(0.01)

# التنظيف
stop_all_processes()
try:
    device.backlight(False)
    device.hide()
except Exception as e:
    print(f"⚠️ Error during final display cleanup: {e}")
try:
    GPIO.cleanup([16, 24, 25, 8])
except Exception as e:
    print(f"⚠️ Error during final GPIO cleanup: {e}")
device.cleanup()