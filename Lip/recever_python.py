import pigpio
import time
import json

RX_GPIO = 27  # BCM Number for GPIO27
MIN_PULSES = 20
MAX_PULSES = 200
MAX_INTERVAL = 5000  # µs, gap to consider end of signal
MIN_PULSE_US = 100    # ignore too-short noise blips
MAX_PULSE_US = 5000   # ignore too-long garbage

class RFDecoder:
    def __init__(self, gpio_pin):
        self.pi = pigpio.pi()
        self.gpio = gpio_pin
        self.last_tick = 0
        self.recording = []
        self.pi.set_mode(self.gpio, pigpio.INPUT)
        self.pi.set_pull_up_down(self.gpio, pigpio.PUD_OFF)
        self.cb = self.pi.callback(self.gpio, pigpio.EITHER_EDGE, self.edge_callback)
        print(json.dumps({"status": "listening", "gpio": self.gpio, "timestamp": time.time()}))

    def edge_callback(self, gpio, level, tick):
        if self.last_tick != 0:
            dt = pigpio.tickDiff(self.last_tick, tick)

            if MIN_PULSE_US <= dt <= MAX_PULSE_US:
                self.recording.append(dt)

            # نهاية الإشارة إن طال الفاصل
            if dt > MAX_INTERVAL:
                if MIN_PULSES <= len(self.recording) <= MAX_PULSES:
                    print(json.dumps({
                        "timestamp": time.time(),
                        "length": len(self.recording),
                        "timings": self.recording
                    }))
                self.recording = []

        self.last_tick = tick

try:
    decoder = RFDecoder(RX_GPIO)
    while True:
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nExiting...")
