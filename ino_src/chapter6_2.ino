// Explicit include for VS Code IntelliSense in .ino files.
#include <Arduino.h>
#include <Servo.h>

Servo servo;

void setup()
{
    servo.attach(8);
}

void loop()
{
    servo.write(0);
    delay(1000);
    servo.write(90);
    delay(1000);
}
