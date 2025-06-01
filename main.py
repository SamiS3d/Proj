from luma.core.render import canvas
from luma.core.interface.serial import spi  # تأكد إن هذا السطر موجود
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

# تحديد المسار الأساسي
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# وظيفة لحفظ الرموز في ملف
def save_key(key):
    count = get_saved_keys_count() + 1
    kar_name = f"kar{count}"
    with open(os.path.join(BASE_DIR, "keys.txt"), "a") as f:
        f.write(f"{kar_name}:{key}\n")
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
        keys = [key for key in keys if key[0] != kar_name]  # إزالة الرمز المطلوب
        with open(os.path.join(BASE_DIR, "keys.txt"), "w") as f:
            for kar_name, key_val in keys:
                f.write(f"{kar_name}:{key_val}\n")
        print(f"🗑️ Deleted key: {kar_name}")
    except Exception as e:
        print(f"⚠️ Error deleting key: {e}")

# وظيفة إرسال الرمز باستخدام rpi_rf
def send_rf_key(code):
    GPIO_PIN = 20
    rfdevice = RFDevice(GPIO_PIN)
    rfdevice.enable_tx()
    try:
        print(f"📤 Sending code: {code}")
        rfdevice.tx_code(int(code))
        print("✅ Done sending.")
    except Exception as e:
        print(f"⚠️ Error sending code: {e}")
    finally:
        rfdevice.cleanup()

# وظيفة إيقاف جميع العمليات
def stop_all_processes():
    global jamming_process, jamming_active
    global jamming_detect_process, jamming_detect_active
    global capture_process, capture_active, capture_bit, recent_outputs

    if jamming_active and jamming_process:
        try:
            jamming_process.send_signal(signal.SIGINT)
            jamming_process.wait(timeout=5)
            print("✅ Jamming stopped (auto).")
        except Exception as e:
            print(f"⚠️ Error stopping Jamming.py: {e}")
        jamming_process = None
        jamming_active = False

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
BLUE = (0, 0, 255)
GRAY = (100, 100, 100)

# الخطوط
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except IOError:
    font = ImageFont.load_default()
    small_font = ImageFont.load_default()

# هيكلية القوائم
main_menu = ["Info", "Security part", "Attack part", "Wifi Test"]
security_menu = ["Jamming Detection", "Captcher My RF kye", "Captcher My RF kye Rolling", "Reuse My RF kye", "Exit"]
attack_menu = ["Jamming", "Captcher RF kye", "Captcher RF kye Rolling", "Reuse My RF kye", "Exit"]
capture_menu = ["24BIT", "32BIT", "64BIT", "128BIT", "Exit"]

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

# وظيفة لقراءة مخرجات العملية
def read_process_output(process):
    while process.poll() is None:
        line = process.stdout.readline()
        if line:
            capture_output.put(line.strip())

# رسم القوائم
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
    global recent_outputs, selecting_key
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.text((15, 20), title, font=font, fill=WHITE)
    
    if title == "Jamming Detection" and jamming_detect_active:
        try:
            while not capture_output.empty():
                line = capture_output.get_nowait()
                recent_outputs.append(line)
                if len(recent_outputs) > 3:
                    recent_outputs.pop(0)
            for i, output in enumerate(recent_outputs):
                draw.text((15, 50 + i * 15), output[:20], font=small_font, fill=WHITE)
            draw.text((15, 100), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
        except queue.Empty:
            for i, output in enumerate(recent_outputs):
                draw.text((15, 50 + i * 15), output[:20], font=small_font, fill=WHITE)
            draw.text((15, 100), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    elif title in ["Captcher My RF kye", "Captcher RF kye"] and selecting_key:
        saved_keys = get_saved_keys()
        for i, (kar_name, key) in enumerate(saved_keys):
            y = 40 + i * 15
            if i == selected_index:
                draw.rectangle((10, y - 2, 117, y + 12), fill=GRAY)
                draw.text((15, y), f"{kar_name}: {key}", font=small_font, fill=BLUE)
            else:
                draw.text((15, y), f"{kar_name}: {key}", font=small_font, fill=WHITE)
        draw.text((15, 100), "Select", font=small_font, fill=BLUE if selected_index == len(saved_keys) else WHITE)
        draw.text((15, 115), "Exit", font=small_font, fill=BLUE if selected_index == len(saved_keys) + 1 else WHITE)
    elif title == "Reuse My RF kye":
        print("📄 Drawing Reuse My RF kye page")
        saved_keys = get_saved_keys()
        print(f"🔑 Saved keys: {saved_keys}")
        if not saved_keys:
            print("⚠️ No keys saved")
            draw.text((15, 40), "No keys saved", font=small_font, fill=WHITE)
            draw.text((15, 100), "Exit", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
        else:
            for i, (kar_name, key) in enumerate(saved_keys):
                print(f"🔑 Drawing key {kar_name}: {key}")
                y = 40 + i * 15
                if i == selected_index:
                    draw.rectangle((10, y - 2, 117, y + 12), fill=GRAY)
                    draw.text((15, y), f"{kar_name}: {key}", font=small_font, fill=BLUE)
                else:
                    draw.text((15, y), f"{kar_name}: {key}", font=small_font, fill=WHITE)
            draw.text((15, 85), "Send", font=small_font, fill=BLUE if selected_index == len(saved_keys) else WHITE)
            draw.text((15, 100), "Delete", font=small_font, fill=BLUE if selected_index == len(saved_keys) + 1 else WHITE)
            draw.text((15, 115), "Exit", font=small_font, fill=BLUE if selected_index == len(saved_keys) + 2 else WHITE)
    else:
        draw.text((15, 80), "Start" if title == "Jamming Detection" else "test", font=small_font, fill=WHITE)
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
    global recent_outputs
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    if capture_active:
        draw.text((15, 20), f"Capturing {capture_bit}", font=font, fill=BLUE)
        while not capture_output.empty():
            line = capture_output.get_nowait()
            recent_outputs.append(line)
            if len(recent_outputs) > 3:
                recent_outputs.pop(0)
        for i, output in enumerate(recent_outputs):
            draw.text((15, 50 + i * 15), output[:20], font=small_font, fill=WHITE)
        draw.text((15, 100), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    else:
        draw_menu(draw, capture_menu, selected_index)

def draw_wifi_test_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.text((15, 50), "Test Wifi", font=font, fill=BLUE if selected_index == 0 else WHITE)
    draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

# الحلقة الرئيسية
running = True
while running:
    vrx = read_adc(0)
    vry = read_adc(1)
    button_state = GPIO.input(16)

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
                selected_index = min(len(saved_keys) + 2, selected_index + 1)
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
        elif current_menu == "security":
            if selected_index == len(security_menu) - 1:  # Exit
                current_menu = "main"
                selected_index = 1
            elif selected_index == 0:  # Jamming Detection
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
                        threading.Thread(target=read_process_output, args=(jamming_detect_process,), daemon=True).start()
                        jamming_detect_active = True
                        print("🚨 Jamming Detection started.")
                    except Exception as e:
                        print(f"⚠️ Error starting Jammingdetect.py: {e}")
            elif selected_index == 1:  # Captcher My RF kye
                current_menu = "capture"
                previous_menu = "security"
                selected_index = 0
            elif selected_index == 3:  # Reuse My RF kye
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
            elif selected_index == 0:  # Jamming
                current_menu = "jamming"
                selected_index = 0
            elif selected_index == 1:  # Captcher RF kye
                current_menu = "capture"
                previous_menu = "attack"
                selected_index = 0
            elif selected_index == 3:  # Reuse My RF kye
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
                    selecting_key = True
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
                        selecting_key = True
            else:
                if selected_index in [0, 1, 2, 3]:  # 24BIT, 32BIT, 64BIT, 128BIT
                    bit_options = ["24", "32", "64", "128"]
                    capture_bit = bit_options[selected_index]
                    stop_all_processes()
                    try:
                        capture_process = subprocess.Popen(
                            ["python3", os.path.join(BASE_DIR, f"recever{capture_bit}.py")],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                        threading.Thread(target=read_process_output, args=(capture_process,), daemon=True).start()
                        capture_active = True
                        print(f"🚨 Capturing {capture_bit} started.")
                    except Exception as e:
                        print(f"⚠️ Error starting recever{capture_bit}.py: {e}")
        elif current_menu in ["security_sub", "attack_sub"] and current_page in ["Captcher My RF kye", "Captcher RF kye"] and selecting_key:
            saved_keys = get_saved_keys()
            if selected_index < len(saved_keys):  # اختيار رمز
                key = saved_keys[selected_index][1]
                key_name = save_key(key)
                print(f"✅ Key saved as {key_name}: {key}")
            elif selected_index == len(saved_keys) + 1:  # Exit
                selecting_key = False
                current_menu = previous_menu
                selected_index = 1
        elif current_menu in ["security_sub", "attack_sub"] and current_page == "Reuse My RF kye":
            saved_keys = get_saved_keys()
            if selected_index < len(saved_keys):  # إرسال رمز
                kar_name, key_val = saved_keys[selected_index]
                send_rf_key(key_val)
                selected_index = 0  # ابقى في نفس الصفحة بعد الإرسال
            elif selected_index == len(saved_keys):  # Send
                pass  # منطق إضافي إذا لزم
            elif selected_index == len(saved_keys) + 1:  # Delete
                if saved_keys:
                    kar_name, _ = saved_keys[selected_index - len(saved_keys)]
                    delete_key(kar_name)
                    selected_index = 0  # إعادة تعيين المؤشر بعد الحذف
            elif selected_index == len(saved_keys) + 2:  # Exit
                current_menu = previous_menu
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

    time.sleep(0.01)

# التنظيف
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
if jamming_detect_active and jamming_detect_process:
    try:
        jamming_detect_process.send_signal(signal.SIGINT)
        jamming_detect_process.wait(timeout=5)
        print("✅ Jamming Detection stopped during cleanup.")
    except Exception as e:
        print(f"⚠️ Error during jamming detect cleanup: {e}")
GPIO.cleanup()
device.cleanup()