#include <Arduino.h>
#include <DHT.h>

DHT dht(4, DHT11);

void setup()
{
    Serial.begin(9600);
    dht.begin();
}

void loop()
{
    int tem = dht.readTemperature();
    int hum = dht.readHumidity();

    Serial.print("Temperature: ");
    Serial.print(tem);
    Serial.print(" °C, Humidity: ");
    Serial.print(hum);
    Serial.println(" %");
    delay(1000);
}
