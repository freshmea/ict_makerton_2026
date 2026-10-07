// Explicit include for VS Code IntelliSense in .ino files.
#include <Arduino.h>

int cds = 0;
int LED = 5;

void setup()
{
    pinMode(6, OUTPUT);
    pinMode(LED, OUTPUT);
    Serial.begin(9600);
}

void loop()
{
    cds = analogRead(A0);
    Serial.print("cds: NoTone");
    Serial.println(cds);
    if (cds > 270)
    {
        Serial.println("cds: Tone");
        Serial.println(cds);
        digitalWrite(LED, HIGH);
        tone(6, 392);
        delay(500);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 392);
        delay(500);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 392);
        delay(500);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 349);
        delay(350);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 466);
        delay(150);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 392);
        delay(500);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 349);
        delay(350);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 466);
        delay(150);
        digitalWrite(LED, LOW);
        delay(100);

        digitalWrite(LED, HIGH);
        tone(6, 392);
        delay(1000);
        digitalWrite(LED, LOW);
    }
    noTone(6);
    digitalWrite(LED, LOW);
}
