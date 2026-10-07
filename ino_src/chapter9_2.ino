// Explicit include for VS Code IntelliSense in .ino files.
#include <Arduino.h>
#include <SoftwareSerial.h>
#include <DFRobotDFPlayerMini.h>

long randNumber;
SoftwareSerial mySerial(10, 11);
DFRobotDFPlayerMini myDFPlayer;

void setup()
{
	mySerial.begin(9600);
	myDFPlayer.begin(mySerial);
	myDFPlayer.volume(20);
	randomSeed(analogRead(A0));
}

void loop()
{
	randNumber = random(1, 21);
	myDFPlayer.play(randNumber);
	delay(5000);
}
