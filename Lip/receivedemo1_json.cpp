#include <wiringPi.h>
#include <stdio.h>
#include <time.h>
#include "rc-switch/RCSwitch.h"

int main(int argc, char *argv[]) {
    printf("{\"timestamp\":%d,\"status\":\"starting\"}\n", (int)time(NULL));

    int PIN = 2;

    if (wiringPiSetup () == -1) {
        printf("{\"timestamp\":%d,\"error\":\"WiringPi not installed.\"}\n", (int)time(NULL));
        return 1;
    }

    pullUpDnControl(PIN, PUD_OFF);

    RCSwitch mySwitch = RCSwitch();
    mySwitch.enableReceive(PIN);

    printf("{\"timestamp\":%d,\"status\":\"listening\"}\n", (int)time(NULL));

    while(true) {
        if (mySwitch.available()) {
            if (mySwitch.getReceivedValue() == 0) {
                printf("{\"timestamp\":%d,\"error\":\"unknown encoding - raw output:\"}\n", (int)time(NULL));

                int len = mySwitch.getReceivedRawLength();
                const unsigned int* timings = mySwitch.getReceivedRawdata();

                printf("{\"timestamp\":%d,\"raw_bits\":\"", (int)time(NULL));

                for (int i = 1; i < len - 1; i += 2) {
                    unsigned int high = timings[i];
                    unsigned int low = timings[i+1];

                    // تمييز بدائي، ممكن تعدله حسب نوع الإشارة
                    if (high > low) {
                        printf("1");
                    } else {
                        printf("0");
                    }
                }
                printf("\"}\n");
            } else {
                printf("{\"timestamp\":%d,\"value\":%lu,\"bitlength\":%i,\"delay\":%i,\"protocol\":%i}\n", 
                    (int)time(NULL), 
                    mySwitch.getReceivedValue(), 
                    mySwitch.getReceivedBitlength(), 
                    mySwitch.getReceivedDelay(), 
                    mySwitch.getReceivedProtocol());
            }

            mySwitch.resetAvailable();
        }

        delay(100);
    }
}
