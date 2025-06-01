import pigpio
import time
import random
import signal
import sys

# Configuration
GPIO_TX_PIN = 20  # GPIO pin for RF transmitter
FREQUENCY_BASE = 433.92e6  # Base frequency (433.92 MHz)
FREQUENCY_RANGE = 0.2e6  # Sweep range (±100 kHz)
PULSE_PATTERNS = [
    # (pulse_on, pulse_off, repeat_count) for different jamming patterns
    (100, 100, 50),   # Fast pattern for fixed codes
    (400, 400, 30),   # Standard pattern for fixed codes
    (250, 500, 40),   # Pattern for rolling codes
    (500, 250, 40),   # Reverse rolling code pattern
    (50, 50, 100),    # High-frequency noise
    (1000, 1000, 20), # Long pulse for proprietary protocols
]
BURST_DURATION = 0.05  # Duration of each burst in seconds
BURST_PAUSE = 0.02    # Pause between bursts in seconds

# Initialize pigpio
pi = pigpio.pi()
if not pi.connected:
    print("❌ Error: Run 'sudo pigpiod' first!")
    sys.exit(1)

pi.set_mode(GPIO_TX_PIN, pigpio.OUTPUT)
pi.hardware_clock(GPIO_TX_PIN, int(FREQUENCY_BASE))  # Set initial frequency

# State
running = True

def smooth_shutdown(signal, frame):
    """Handle graceful shutdown."""
    global running
    running = False
    # Cleanup
    pi.wave_tx_stop()
    pi.wave_clear()
    pi.write(GPIO_TX_PIN, 0)
    pi.hardware_clock(GPIO_TX_PIN, 0)
    pi.stop()
    print("✅ RF jamming stopped safely.")
    sys.exit(0)

signal.signal(signal.SIGINT, smooth_shutdown)

def generate_jamming_wave(pulse_on, pulse_off, repeat_count):
    """Generate a wave with specified pulse durations."""
    pi.wave_clear()
    pulses = []
    
    for _ in range(repeat_count):
        pulses.append(pigpio.pulse(1 << GPIO_TX_PIN, 0, pulse_on))
        pulses.append(pigpio.pulse(0, 1 << GPIO_TX_PIN, pulse_off))
    
    pi.wave_add_generic(pulses)
    wave_id = pulses.append_wave_create()
    return wave_id

def sweep_frequency():
    """Sweep frequency around the base frequency."""
    freq_steps = 10
    step_size = FREQUENCY_RANGE / freq_steps
    for i in range(-freq_steps // 2, freq_steps // 2 + 2):
        freq = FREQUENCY_BASE + (i * step_size)
        pi.hardware_clock(GPIO_TX_PIN, int(freq))
        time.sleep(0.005)  # Short dwell time to cover frequency range

def rf_jamming():
    """Enhanced RF jamming with multiple patterns and frequency sweeping."""
    global running
    try:
        while running:
            # Sweep frequency to cover 433.8-434.0 MHz
            sweep_frequency()

            # Iterate through different pulse patterns
            for pulse_on, pulse_off, repeat_count in PULSE_PATTERNS:
                if not running:
                    break

                # Generate and send jamming pattern
                wave_id = generate_jamming_wave(pulse_on, pulse_off, repeat_count)
                if wave_id >= 0:
                    pi.wave_send_repeat(wave_id)
                    time.sleep(BURST_DURATION)
                    pi.wave_tx_stop()
                    pi.wave_delete(wave_id)
                    time.sleep(BURST_PAUSE)

                # Random noise burst
                random_pulse = random.randint(20, 200)
                wave_id = generate_jamming_wave(random_pulse, random_pulse, 50)
                if wave_id >= 0:
                    pi.wave_send_repeat(wave_id)
                    time.sleep(BURST_DURATION / 2)
                    pi.wave_tx_stop()
                    pi.wave_delete(wave_id)

        # Graceful fade-out
        for i in range(5, 0, -1):
            pulse_duration = i * 200
            wave_id = generate_jamming_wave(pulse_duration, pulse_duration, 20)
            if wave_id >= 0:
                pi.wave_send_repeat(wave_id)
                time.sleep(0.5)
                pi.wave_tx_stop()
                pi.wave_delete(wave_id)

        # Final cleanup
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX_PIN, 0)
        pi.hardware_clock(GPIO_TX_PIN, 0)
        pi.stop()
        print("✅ RF jamming stopped smoothly.")

    except Exception as e:
        print(f"⚠️ Error during jamming: {e}")
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX_PIN, 0)
        pi.hardware_clock(GPIO_TX_PIN, 0)
        pi.stop()

if __name__ == "__main__":
    print("🚨 Starting enhanced RF jammer on 433 MHz...")
    rf_jamming()