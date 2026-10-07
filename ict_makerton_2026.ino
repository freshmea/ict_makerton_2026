// Explicit include for VS Code IntelliSense in .ino files.
#include <Adafruit_NeoPixel.h>
#include <Arduino.h>
#include <DFRobotDFPlayerMini.h>
#include <DHT.h>
#include <SoftwareSerial.h>

SoftwareSerial mySerial(10, 11);
DFRobotDFPlayerMini myDFPlayer;
Adafruit_NeoPixel strip(4, 7, NEO_GRB + NEO_KHZ800);
DHT dht(4, DHT11);

int echo = 12;
int trig = 13;

void setup()
{
  strip.begin();
  mySerial.begin(9600);
  myDFPlayer.begin(mySerial);
  dht.begin();
  myDFPlayer.volume(20);
  pinMode(trig, OUTPUT);
  pinMode(echo, INPUT);
  randomSeed(analogRead(A0));
}

void loop()
{
  long r1 = random(256);
  long r2 = random(256);
  long r3 = random(256);

  for (int i = 0; i < 4; i++)
  {
    strip.setPixelColor(i, r1, r2, r3);
  }

  strip.show();
  delay(500);

  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);

  long duration = pulseIn(echo, HIGH);
  long distance = (duration * 340) / 2 / 10000;

  int hum = dht.readHumidity();

  if (distance < 30)
  {
    if (hum < 40)
    {
      for (int i = 0; i < 4; i++)
      {
        strip.setPixelColor(i, 200, 0, 0);
      }
      myDFPlayer.play(1);
      strip.show();
    }
    else
    {
      for (int i = 0; i < 4; i++)
      {
        strip.setPixelColor(i, 0, 0, 200);
      }
      myDFPlayer.play(2);
      strip.show();
    }
  }

  delay(3000);
}
