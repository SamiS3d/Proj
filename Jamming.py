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
    running = False

signal.signal(signal.SIGINT, smooth_shutdown)

def rf_jamming():
    global running
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

        for i in range(5, 0, -1):
            pulse_duration = i * 200
            pi.wave_clear()

            pulses = [
                pigpio.pulse(1 << GPIO_TX, 0, pulse_duration),
                pigpio.pulse(0, 1 << GPIO_TX, pulse_duration)
            ]

            pi.wave_add_generic(pulses)
            wave_id = pi.wave_create()

            if wave_id >= 0:
                pi.wave_send_repeat(wave_id)
                time.sleep(0.5)
                pi.wave_delete(wave_id)

        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX, 0)
        pi.stop()

        print("✅ RF Jamming stopped smoothly. Receiver is safe now.")

    except Exception as e:
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX, 0)
        pi.stop()

if __name__ == "__main__":
    rf_jamming()