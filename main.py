import time
import smbus2
import RPi.GPIO as GPIO
import subprocess
import signal
import os
import psutil
import threading
import queue
from luma.core.interface.serial import spi
from luma.lcd.device import st7735
from PIL import ImageFont
from luma.core.render import canvas

# تحديد المسار الأساسي
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# تهيئة الشاشة ST7735
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_CS=8)
device = st7735(serial, width=128, height=128, rotate=45)
device.backlight(True)

# إعداد GPIO و I2C للجويستيك
GPIO.setmode(GPIO.BCM)
GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Joystick button
GPIO.setup(24, GPIO.OUT)  # DC
GPIO.setup(25, GPIO.OUT)  # RST
GPIO.setup(8, GPIO.OUT)   # CS
bus = smbus2.SMBus(1)
ADS1115_ADDRESS = 0x48

# الخطوط
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except IOError:
    font = ImageFont.load_default()
    small_font = ImageFont.load_default()

# الألوان
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)
GRAY = (100, 100, 100)

# هيكلية القوائم
main_menu = ["Info", "Security part", "Attack part", "Wifi Test"]
security_submenu = ["Jamming Detection", "Captcher My RF kye", "Captcher My RF kye Rolling", "Reuse My RF kye", "Exit"]
attack_submenu = ["Jamming", "Jamming + Capture", "Captcher RF kye", "Captcher RF kye Rolling", "Reuse My RF kye", "Exit"]
capture_menu = ["24BIT", "32BIT", "520BIT", "RFID", "Exit"]
key_action_menu = ["Send", "Delete", "Exit"]

# متغيرات الحالة
current_menu = "main"
selected_index = 0
last_button_state = True
last_move_time = 0
move_delay = 0.2
current_page = None
previous_menu = None
selecting_key = False
selected_key = None
jamming_process = None
jamming_active = False
capture_process = None
capture_active = False
capture_bit = None
jamming_capture_process = None
jamming_capture_active = False
capture_output = queue.Queue()
recent_outputs = []

# وظيفة قراءة ADC للجويستيك
def read_adc(channel):
    try:
        config = 0xC183 | (channel << 12)
        bus.write_i2c_block_data(ADS1115_ADDRESS, 0x01, [(config >> 8) & 0xFF, config & 0xFF])
        time.sleep(0.01)
        data = bus.read_i2c_block_data(ADS1115_ADDRESS, 0x00, 2)
        return (data[0] << 8) | data[1]
    except Exception:
        return 0

# وظيفة إعادة تهيئة الشاشة
def reinitialize_display():
    global device
    try:
        serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, gpio_CS=8)
        device = st7735(serial, width=128, height=128, rotate=45)
        device.backlight(True)
        print("🖥️ Re-initialized display")
    except Exception as e:
        print(f"⚠️ Error re-initializing display: {e}")

# وظيفة تنظيف العمليات والـ GPIO
def stop_all_processes():
    global jamming_process, jamming_active
    global capture_process, capture_active, capture_bit
    global jamming_capture_process, jamming_capture_active
    global recent_outputs

    # إيقاف Jamming
    if jamming_active and jamming_process:
        try:
            jamming_process.send_signal(signal.SIGINT)
            jamming_process.wait(timeout=5)
            print("✅ Jamming stopped.")
        except Exception as e:
            print(f"⚠️ Error stopping Jamming: {e}")
        jamming_process = None
        jamming_active = False

    # إيقاف Capture
    if capture_active and capture_process:
        try:
            capture_process.send_signal(signal.SIGINT)
            capture_process.wait(timeout=5)
            print(f"✅ Capture {capture_bit} stopped.")
        except Exception as e:
            print(f"⚠️ Error stopping capture: {e}")
        capture_process = None
        capture_active = False
        capture_bit = None
        recent_outputs = []

    # إيقاف Jamming + Capture
    if jamming_capture_active and jamming_capture_process:
        try:
            jamming_capture_process.send_signal(signal.SIGINT)
            jamming_capture_process.wait(timeout=5)
            print("✅ Jamming + Capture stopped.")
        except Exception as e:
            print(f"⚠️ Error stopping JammingCapture: {e}")
        jamming_capture_process = None
        jamming_capture_active = False
        recent_outputs = []

    # تنظيف العمليات الزائدة
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if 'python3' in proc.info['name'] and any(
                x in proc.cmdline() for x in ['recever24.py', 'recever32.py', 'recever520.py', 'receverRFID.py', 'Jamming.py', 'JammingCapture.py']
            ):
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=5)
                print(f"🧹 Terminated stray process: {proc.info['name']}")
    except Exception as e:
        print(f"⚠️ Error terminating stray processes: {e}")

    # إعادة تشغيل pigpiod
    try:
        subprocess.run(["sudo", "pkill", "pigpiod"], check=True)
        time.sleep(0.5)
        subprocess.run(["sudo", "pigpiod"], check=True)
        print("🔄 Restarted pigpiod daemon")
    except Exception as e:
        print(f"⚠️ Error restarting pigpiod: {e}")

    # تنظيف GPIO
    try:
        GPIO.cleanup([20, 21, 16, 24, 25, 8])
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(24, GPIO.OUT)
        GPIO.setup(25, GPIO.OUT)
        GPIO.setup(8, GPIO.OUT)
        print("🧹 Cleaned and re-initialized GPIO pins")
    except Exception as e:
        print(f"⚠️ Error cleaning GPIO: {e}")

# وظيفة قراءة مخرجات العملية
def read_process_output(process, output_queue):
    try:
        while process.poll() is None:
            line = process.stdout.readline()
            if line:
                output_queue.put(line.strip())
    except Exception as e:
        print(f"⚠️ Error reading process output: {e}")

# وظائف الرسم
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
        "By: Sami & Ahmed",
        "Exit"
    ]
    for i, line in enumerate(lines):
        y = 20 + i * 25
        color = BLUE if i == 3 and selected_index == 0 else WHITE
        draw.text((10, y), line, font=small_font, fill=color)

def draw_jamming_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    if jamming_active:
        draw.text((15, 40), "Jamming Active", font=font, fill=BLUE)
        draw.text((15, 80), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    else:
        draw.text((15, 40), "Start Jamming", font=font, fill=BLUE if selected_index == 0 else WHITE)
        draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

def draw_jamming_capture_page(draw):
    global recent_outputs
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    if jamming_capture_active:
        draw.text((15, 20), "Jamming + Capture", font=font, fill=BLUE)
        try:
            while not capture_output.empty():
                line = capture_output.get_nowait()
                recent_outputs.append(line)
                if len(recent_outputs) > 3:
                    recent_outputs.pop(0)
            for i, output in enumerate(recent_outputs):
                draw.text((15, 50 + i * 15), output[:20], font=small_font, fill=WHITE)
        except queue.Empty:
            for i, output in enumerate(recent_outputs):
                draw.text((15, 50 + i * 15), output[:20], font=small_font, fill=WHITE)
        draw.text((15, 100), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    else:
        draw.text((15, 40), "Start Jam+Cap", font=font, fill=BLUE if selected_index == 0 else WHITE)
        draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

def draw_capture_page(draw):
    global recent_outputs
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    if capture_active:
        draw.text((15, 20), f"Capturing {capture_bit}", font=font, fill=BLUE)
        try:
            while not capture_output.empty():
                line = capture_output.get_nowait()
                recent_outputs.append(line)
                if len(recent_outputs) > 3:
                    recent_outputs.pop(0)
        except queue.Empty:
            pass
        for i, output in enumerate(recent_outputs):
            draw.text((15, 50 + i * 15), output[:20], font=small_font, fill=WHITE)
        draw.text((15, 100), "Stop", font=small_font, fill=BLUE if selected_index == 0 else WHITE)
    else:
        draw_menu(draw, capture_menu, selected_index)

def draw_wifi_test_page(draw):
    draw.rectangle((0, 0, 127, 127), fill=BLACK)
    draw.text((15, 40), "Wifi Test", font=font, fill=BLUE if selected_index == 0 else WHITE)
    draw.text((15, 80), "Exit", font=small_font, fill=BLUE if selected_index == 1 else WHITE)

# الحلقة الرئيسية
running = True
while running:
    try:
        vrx = read_adc(0)
        vry = read_adc(1)
        button_state = GPIO.input(16)
    except Exception as e:
        print(f"⚠️ GPIO Error: {e}")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(24, GPIO.OUT)
        GPIO.setup(25, GPIO.OUT)
        GPIO.setup(8, GPIO.OUT)
        vrx, vry = 0, 0
        button_state = True

    current_time = time.time()
    if current_time - last_move_time > move_delay:
        if vry < 10000:
            selected_index = max(0, selected_index - 1)
            last_move_time = current_time
        elif vry > 60000:
            if current_menu == "main":
                selected_index = min(len(main_menu) - 1, selected_index + 1)
            elif current_menu == "security":
                selected_index = min(len(security_submenu) - 1, selected_index + 1)
            elif current_menu == "attack":
                selected_index = min(len(attack_submenu) - 1, selected_index + 1)
            elif current_menu == "capture":
                selected_index = min(len(capture_menu) - 1, selected_index + 1)
            elif current_menu in ["jamming", "jamming_capture", "wifi"]:
                selected_index = min(1, selected_index + 1)
            last_move_time = current_time

    if button_state == False and last_button_state == True:
        print(f"🔄 Menu: {current_menu}, Index: {selected_index}")
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
            if selected_index == len(security_submenu) - 1:
                current_menu = "main"
                selected_index = 1
            elif selected_index == 1:
                current_menu = "capture"
                previous_menu = "security"
                selected_index = 0
                recent_outputs = []
        elif current_menu == "attack":
            if selected_index == len(attack_submenu) - 1:
                current_menu = "main"
                selected_index = 2
            elif selected_index == 0:
                current_menu = "jamming"
                selected_index = 0
            elif selected_index == 1:
                current_menu = "jamming_capture"
                selected_index = 0
                recent_outputs = []
            elif selected_index == 2:
                current_menu = "capture"
                previous_menu = "attack"
                selected_index = 0
                recent_outputs = []
        elif current_menu == "jamming":
            if selected_index == 0:
                if jamming_active:
                    if jamming_process:
                        try:
                            jamming_process.send_signal(signal.SIGINT)
                            jamming_process.wait(timeout=5)
                            print("✅ Jamming stopped.")
                        except Exception as e:
                            print(f"⚠️ Error stopping Jamming: {e}")
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
                        threading.Thread(target=read_process_output, args=(jamming_process, capture_output), daemon=True).start()
                        jamming_active = True
                        print("🚨 Jamming started.")
                    except Exception as e:
                        print(f"⚠️ Error starting Jamming: {e}")
            elif selected_index == 1:
                if jamming_active and jamming_process:
                    try:
                        jamming_process.send_signal(signal.SIGINT)
                        jamming_process.wait(timeout=5)
                        print("✅ Jamming stopped.")
                    except Exception as e:
                        print(f"⚠️ Error stopping Jamming: {e}")
                    jamming_process = None
                    jamming_active = False
                current_menu = "attack"
                selected_index = 0
        elif current_menu == "jamming_capture":
            if selected_index == 0:
                if jamming_capture_active:
                    if jamming_capture_process:
                        try:
                            jamming_capture_process.send_signal(signal.SIGINT)
                            jamming_capture_process.wait(timeout=5)
                            print("✅ Jamming + Capture stopped.")
                        except Exception as e:
                            print(f"⚠️ Error stopping JammingCapture: {e}")
                        jamming_capture_process = None
                        jamming_capture_active = False
                        recent_outputs = []
                else:
                    try:
                        stop_all_processes()
                        jamming_capture_process = subprocess.Popen(
                            ["python3", os.path.join(BASE_DIR, "JammingCapture.py")],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                        threading.Thread(target=read_process_output, args=(jamming_capture_process, capture_output), daemon=True).start()
                        jamming_capture_active = True
                        print("🚨 Jamming + Capture started.")
                    except Exception as e:
                        print(f"⚠️ Error starting JammingCapture: {e}")
            elif selected_index == 1:
                if jamming_capture_active and jamming_capture_process:
                    try:
                        jamming_capture_process.send_signal(signal.SIGINT)
                        jamming_capture_process.wait(timeout=5)
                        print("✅ Jamming + Capture stopped.")
                    except Exception as e:
                        print(f"⚠️ Error stopping JammingCapture: {e}")
                    jamming_capture_process = None
                    jamming_capture_active = False
                    recent_outputs = []
                current_menu = "attack"
                selected_index = 1
        elif current_menu == "capture":
            if selected_index == len(capture_menu) - 1:
                if capture_active and capture_process:
                    try:
                        capture_process.send_signal(signal.SIGINT)
                        capture_process.wait(timeout=5)
                        print(f"✅ Capture {capture_bit} stopped.")
                    except Exception as e:
                        print(f"⚠️ Error stopping capture: {e}")
                    capture_process = None
                    capture_active = False
                    capture_bit = None
                    recent_outputs = []
                stop_all_processes()
                current_menu = previous_menu
                selected_index = 2 if previous_menu == "attack" else 1
            elif capture_active:
                if selected_index == 0:
                    if capture_process:
                        try:
                            capture_process.send_signal(signal.SIGINT)
                            capture_process.wait(timeout=5)
                            print(f"✅ Capture {capture_bit} stopped.")
                        except Exception as e:
                            print(f"⚠️ Error stopping capture: {e}")
                        capture_process = None
                        capture_active = False
                        capture_bit = None
                        recent_outputs = []
                    stop_all_processes()
            else:
                if selected_index in [0, 1, 2, 3]:
                    bit_options = ["24", "32", "520", "RFID"]
                    capture_bit = bit_options[selected_index]
                    try:
                        stop_all_processes()
                        capture_process = subprocess.Popen(
                            ["python3", os.path.join(BASE_DIR, f"recever{capture_bit}.py")],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                        threading.Thread(target=read_process_output, args=(capture_process, capture_output), daemon=True).start()
                        capture_active = True
                        print(f"🚨 Capture {capture_bit} started.")
                    except Exception as e:
                        print(f"⚠️ Error starting recever{capture_bit}: {e}")
                        capture_process = None
                        capture_active = False
                        capture_bit = None
                        stop_all_processes()
        elif current_menu == "info":
            if selected_index == 0:
                current_menu = "main"
                selected_index = 0
        elif current_menu == "wifi":
            if selected_index == 1:
                current_menu = "main"
                selected_index = 3

    last_button_state = button_state

    try:
        with canvas(device) as draw:
            if current_menu == "main":
                draw_menu(draw, main_menu, selected_index)
            elif current_menu == "security":
                draw_menu(draw, security_submenu, selected_index)
            elif current_menu == "attack":
                draw_menu(draw, attack_submenu, selected_index)
            elif current_menu == "info":
                draw_info_page(draw)
            elif current_menu == "jamming":
                draw_jamming_page(draw)
            elif current_menu == "jamming_capture":
                draw_jamming_capture_page(draw)
            elif current_menu == "capture":
                draw_capture_page(draw)
            elif current_menu == "wifi":
                draw_wifi_test_page(draw)
    except Exception as e:
        print(f"⚠️ Error drawing: {e}")
        reinitialize_display()

    time.sleep(0.01)

# التنظيف
stop_all_processes()
GPIO.cleanup([16, 20, 21, 24, 25, 8])
device.cleanup()
print("🛑 Program terminated.")