#include <Arduino.h>
#include <LiquidCrystal_I2C.h>

int echo = 12;
int trig = 13;
LiquidCrystal_I2C lcd(0x27, 16, 2);


void setup() {
    pinMode(echo, INPUT);
    pinMode(trig, OUTPUT);
    lcd.init();
    lcd.backlight();
}

void loop() {
    digitalWrite(trig, LOW);
    delayMicroseconds(2);
    digitalWrite(trig, HIGH);
    delayMicroseconds(10);
    digitalWrite(trig, LOW);

    long duration = pulseIn(echo, HIGH);
    long distance = duration * 0.034 / 2;

    lcd.setCursor(0, 0);
    lcd.print("Distance: ");
    lcd.print(distance);
    lcd.print(" cm");

    delay(500);
}
