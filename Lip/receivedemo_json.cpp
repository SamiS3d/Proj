#include <stdio.h>
#include <time.h>
#include "rc-switch/RCSwitch.h"

int main(int argc, char *argv[]) {
    printf("{\"timestamp\":%d,\"status\":\"starting\"}\n", (int)time(NULL));

    int PIN = 2;

    if (wiringPiSetup() == -1) {
        printf("{\"timestamp\":%d,\"error\":\"WiringPi not installed.\"}\n", (int)time(NULL));
        return 1;
    }

    pullUpDnControl(PIN, PUD_OFF);

    RCSwitch mySwitch = RCSwitch();
    mySwitch.enableReceive(PIN);

    printf("{\"timestamp\":%d,\"status\":\"listening\"}\n", (int)time(NULL));

    while (true) {
        if (mySwitch.available()) {
            int len = mySwitch.getReceivedBitlength();
            const unsigned int* timings = mySwitch.getReceivedRawdata();
            int timingCount = mySwitch.getReceivedDelay() * len * 2;

            printf("{\"timestamp\":%d,\"bitlength\":%d,\"raw_bits\":\"", (int)time(NULL), len);

            for (int i = 1; i < len * 2 - 1; i += 2) {
                unsigned int high = timings[i];
                unsigned int low = timings[i + 1];

                if (high > low) {
                    printf("1");
                } else {
                    printf("0");
                }
            }
            printf("\"}\n");

            mySwitch.resetAvailable();
        }

        delay(100);
    }
}
