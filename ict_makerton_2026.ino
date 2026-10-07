#include <Adafruit_NeoPixel.h>
#include <Arduino.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);
DHT dht(4, DHT11);
Adafruit_NeoPixel strip(4, 7, NEO_GRB + NEO_KHZ800);

void setup()
{
  lcd.init();
  lcd.backlight();
  dht.begin();
  strip.begin();
  strip.setBrightness(127);
}

void loop()
{
  int hum = dht.readHumidity();

  lcd.print("hum : ");
  lcd.print(hum);

  if (hum < 0 || hum > 100)
  {
    strip.setPixelColor(0, 0, 0, 0);
    strip.setPixelColor(1, 0, 0, 0);
    strip.setPixelColor(2, 0, 0, 0);
    strip.setPixelColor(3, 0, 0, 0);
    strip.show();
    delay(10);
  }

  if (hum >= 0 && hum <= 50)
  {
    strip.setPixelColor(0, 127, 0, 0);
    strip.setPixelColor(1, 127, 0, 0);
    strip.setPixelColor(2, 127, 0, 0);
    strip.setPixelColor(3, 127, 0, 0);
    strip.show();
    delay(10);
  }

  if (hum > 50 && hum <= 75)
  {
    strip.setPixelColor(0, 0, 127, 0);
    strip.setPixelColor(1, 0, 127, 0);
    strip.setPixelColor(2, 0, 127, 0);
    strip.setPixelColor(3, 0, 127, 0);
    strip.show();
    delay(10);
  }

  if (hum > 75 && hum <= 100)
  {
    strip.setPixelColor(0, 0, 0, 127);
    strip.setPixelColor(1, 0, 0, 127);
    strip.setPixelColor(2, 0, 0, 127);
    strip.setPixelColor(3, 0, 0, 127);
    strip.show();
    delay(10);
  }

  delay(500);
  lcd.clear();
}
