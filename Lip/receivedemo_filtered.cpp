#include <stdio.h>
#include <time.h>
#include "rc-switch/RCSwitch.h"

int main(int argc, char *argv[]) {
    printf("{\"timestamp\":%ld,\"status\":\"starting\"}\n", time(NULL));

    const int PIN = 2; // WiringPi 2 = GPIO27

    if (wiringPiSetup() == -1) {
        printf("{\"timestamp\":%ld,\"error\":\"WiringPi not installed.\"}\n", time(NULL));
        return 1;
    }

    pullUpDnControl(PIN, PUD_DOWN);  // شد لأسفل لتقليل النويز

    RCSwitch mySwitch = RCSwitch();

    mySwitch.setPulseLength(300);       // قياسي: جرب تغيره لـ 320 أو 350 أو 400 حسب المفتاح
    mySwitch.setReceiveTolerance(70);   // سماحية معتدلة
    mySwitch.enableReceive(PIN);

    printf("{\"timestamp\":%ld,\"status\":\"listening\",\"gpio\":27}\n", time(NULL));

    while (true) {
        if (mySwitch.available()) {
            int bitLen = mySwitch.getReceivedBitlength();
            const unsigned int* timings = mySwitch.getReceivedRawdata();
            unsigned int delay = mySwitch.getReceivedDelay();

            // فلترة خفيفة جدًا
            if (bitLen < 8 || bitLen > 100) {
                mySwitch.resetAvailable();
                continue;
            }

            // عرض الإشارة الخام
            printf("{\"timestamp\":%ld,\"bitlength\":%d,\"delay\":%u,\"timings\":[", time(NULL), bitLen, delay);
            for (int i = 0; i < bitLen * 2; ++i) {
                printf("%u", timings[i]);
                if (i < bitLen * 2 - 1) printf(",");
            }
            printf("]}\n");

            mySwitch.resetAvailable();
        }

        delay(50);
    }

    return 0;
}
