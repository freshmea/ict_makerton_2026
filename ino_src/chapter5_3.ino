#include <Arduino.h>

int cds = 0;

void setup()
{
    pinMode(6, OUTPUT);
}

void loop()
{
    cds = analogRead(A0);
    if (cds > 270) {
        tone(6, 131);
        delay(1000);
        tone(6, 147);
        delay(1000);
        tone(6, 165);
        delay(1000);
        tone(6, 175);
        delay(1000);
        noTone(6);
    }
    noTone(6);
}
