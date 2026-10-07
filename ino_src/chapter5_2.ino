#include <Arduino.h>

void setup()
{
    pinMode(6, OUTPUT);
}

void loop()
{
    tone(6, 131);
    delay(1000);
    tone(6, 147);
    delay(1000);
    tone(6, 165);
    delay(1000);
    tone(6, 175);
    delay(1000);
    noTone(6);
    delay(1000);
}
