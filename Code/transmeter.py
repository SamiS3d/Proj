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

