#include <stdio.h>
#include "rc-switch/RCSwitch.h"

int main(int argc, char *argv[]) {
      
    printf("Starting senddemo\n");
    printf("Make sure you have connected the 433Mhz sender data pin to WiringPi pin 0 (real pin 11). See: https://pinout.xyz/pinout/pin11_gpio17\n");
    printf("\n");

    int PIN = 0;

    if (wiringPiSetup () == -1) {
        printf("ERROR: WiringPi not installed. Make sure you have WiringPi installed.\n");
        printf("Quick tutorial:\n\n");
        printf("    sudo apt-get install git\n");
        printf("    cd ~/\n");
        printf("    git clone git://git.drogon.net/wiringPi\n");
        printf("    cd wiringPi\n");
        printf("    ./build\n\n");
        return 1;
    }

    RCSwitch mySwitch = RCSwitch();

    mySwitch.enableTransmit(PIN);

    
    mySwitch.setProtocol(1);
    

    printf("Sending something\n");
    mySwitch.send(320210605072, 48);

    printf("Done\n");

    return 0;
}
