// Explicit include for VS Code IntelliSense in .ino files.
#include <Arduino.h>

int cds = 0;

void setup()
{
    Serial.begin(9600);
}

void loop()
{
    cds = analogRead(A0);
    Serial.print("cds: ");
    Serial.println(cds);
    delay(500);
}
