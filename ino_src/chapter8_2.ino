#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

Adafruit_NeoPixel strip(4, 7);

void setup() {
  strip.begin();
  strip.show();
}

void loop() {
    strip.setPixelColor(0, 127, 0, 0);
    strip.setPixelColor(1, 0, 127, 0);
    strip.setPixelColor(2, 0, 0, 127);
    strip.setPixelColor(3, 127, 127, 127);

    strip.show();
    delay(1000);

    strip.clear();
    strip.show();
    delay(1000);
}