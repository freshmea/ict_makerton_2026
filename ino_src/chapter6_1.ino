// Explicit include for VS Code IntelliSense in .ino files.
#include <Arduino.h>

int soil;

void setup()
{
    Serial.begin(9600);
}

void loop()
{
    soil = analogRead(A1);
    Serial.print("moisture:");
    Serial.println(soil);
    delay(500);
}
