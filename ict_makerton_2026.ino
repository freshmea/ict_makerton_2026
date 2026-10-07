#include <Arduino.h>
#include <DFRobotDFPlayerMini.h>
#include <SoftwareSerial.h>

SoftwareSerial mySoftwareSerial(10, 11); // RX, TX
DFRobotDFPlayerMini myDFPlayer;

void setup()
{
  mySoftwareSerial.begin(9600);
  myDFPlayer.begin(mySoftwareSerial);
  myDFPlayer.volume(20);
}

void loop()
{
  myDFPlayer.play(1);
  delay(5000);
  myDFPlayer.play(2);
  delay(5000);
  myDFPlayer.play(3);
  delay(5000);
}
