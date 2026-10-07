#include <Arduino.h>
#include <Servo.h>
Servo servo;

int soil;
int cds = 0;
int led = 5;

void setup()
{
    pinMode(led, OUTPUT);
    servo.attach(8);
    Serial.begin(9600);
}

void loop()
{
    soil = analogRead(A1);
    cds = analogRead(A0);
    if(cds > 300){
        digitalWrite(led, HIGH);
    } else {
        digitalWrite(led, LOW);
    }

    if(soil < 500){
        servo.write(0);
        delay(500);
    } else {
        servo.write(90);
        delay(500);
    }
}
