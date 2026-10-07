// Explicit include for VS Code IntelliSense in .ino files.
#include <Arduino.h>
#include <Servo.h>

Servo servoMotor;

int moistureSensorPin = A1;
int switchPin = 2;
int buzzerPin = 6;
int servoPin = 8;

int warningMuted = 0;

void setup()
{
  pinMode(switchPin, INPUT_PULLUP);
  pinMode(buzzerPin, OUTPUT);

  servoMotor.attach(servoPin);
  servoMotor.write(0);

  Serial.begin(9600);
}

void loop()
{
  int moistureValue = analogRead(moistureSensorPin);

  if (moistureValue >= 500)
  {
    warningMuted = 0;
    noTone(buzzerPin);
    servoMotor.write(0);
    delay(100);
  }
  else if (digitalRead(switchPin) == LOW)
  {
    warningMuted = 1;
    noTone(buzzerPin);
    servoMotor.write(90);
    delay(100);
  }
  else if (warningMuted == 0)
  {
    servoMotor.write(0);
    tone(buzzerPin, 2000);
    delay(200);
    noTone(buzzerPin);
    delay(800);
  }
  else
  {
    noTone(buzzerPin);
    servoMotor.write(90);
    delay(100);
  }

  Serial.print("moisture: ");
  Serial.print(moistureValue);
  Serial.print(", alertMuted: ");
  if (warningMuted == 1)
  {
    Serial.println("YES");
  }
  else
  {
    Serial.println("NO");
  }
}
