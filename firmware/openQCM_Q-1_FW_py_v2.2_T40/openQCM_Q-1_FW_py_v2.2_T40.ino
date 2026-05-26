/***********************************************************************************************

   LICENSE
   Copyright (C) 2018 openQCM
   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   You should have received a copy of the GNU General Public License
   along with this program.  If not, see http://www.gnu.org/licenses/gpl-3.0.txt
  --------------------------------------------------------------------------------
   OPENQCM Q-1 - Quartz Crystal Microbalance with dissipation monitoring
   openQCM is the unique opensource quartz crystal microbalance http://openqcm.com/
   
   ELECTRONICS
     - board and firmware designed for teensy 4.0 development board
       https://www.pjrc.com/store/teensy40.html
     - DDS/DAC Synthesizer AD9851
     - phase comparator AD8302
     - I2C digital potentiometer AD5251+
     - MCP9808 temperature sensor

   version  ver 2.1 T40
   tag      // V2.1_T40
   date     September 2021
   author   openQCM team
   --------------------------------------------------------------------------------

   CHANGES ver 2.2 T40
   - bug fix: value and value2 reset to zero at each loop 

   CHANGES ver 2.1 T40
   - Using ADC library by pedvide 
     https://pedvide.github.io/ADC/
     https://github.com/pedvide/ADC

   
   - changed pot value for compatibility with openQCM Q-1 shield @5VDC   
   - changed ADC delay microseconds > 100 us
   - changed ADC avaeraging sample  > 32 sample
   - changed the type of phase and mag to double
   - changed included library for MCP9808 temperature sensor in skecth directory v1.0

   TODO
   - I2C replace standard i2c library with Teensy i2c custom library i2c_t3.h
   Brian (nox771) New I2C library for Teensy3
   https://github.com/nox771/i2c_t3
   - ADC libraries https://github.com/pedvide/ADC

   CREDIT:
   - based on the work made by Brett Killion on Hackaday
     https://hackaday.io/project/10021-arduino-network-analyzer
   - Teensy 4.0 is  developed by Paul Stoffregen working at PJRC
     https://www.pjrc.com/store/teensy40.html
   - MCP9808 I2c temperature sensor dirver is developed by Adafruit 
   Written by Kevin Townsend/Limor Fried for Adafruit Industries.

 ***********************************************************************************************/

/************************** LIBRARIES **************************/
#include<Wire.h>
// libraries included in /src folder
# include "src/Adafruit_MCP9808.h"
// V2.1_T40 using ADC library by pedvide
# include "src/ADC/ADC.h"
# include "src/ADC/ADC_util.h"
#include <EEPROM.h>

/*************************** EEPROM SERIAL NUMBER ***************************/
// EEPROM layout: [0]=MAGIC(0xA5) [1]=SERIES [2]=SERIAL_H [3]=SERIAL_L
// Written once by the SerialNumber programmer sketch, read here on command 'S'
#define ADDR_MAGIC        0
#define ADDR_SERIES       1
#define ADDR_SERIAL_HIGH  2
#define ADDR_SERIAL_LOW   3
#define MAGIC_BYTE        0xA5

/*************************** DEFINE ***************************/
// firmware version (queried by Python software with 'F' command)
#define FW_VERSION "2.2"
// potentiometer AD5252 I2C address is 0x2C(44)
#define ADDRESS 0x2C
// potentiometer AD5252 default value for compatibility with openQCM Q-1 shield @5VDC 
#define POT_VALUE 240
// reference clock
#define REFCLK 125000000

// V2.1_T40 ADC averaging and resolution define 
#define AVERAGING   1
#define RESOLUTION 12

/*************************** VARIABLE DECLARATION ***************************/

// current input frequency
long freq = 0;

// V2.1_T40 DDS Synthesizer AD9851 pin function
int WCLK = 3;
int DATA = 4;
int FQ_UD = 2;

// frequency tuning word
long FTW;
float temp_FTW; // temporary variable

/* 
 *  TODO DELETE OLD 
// phase comparator AD8302 pinout
int AD8302_PHASE = 20;
int AD8302_MAG = 37;
//int AD83202_REF = 17;
int AD83202_REF = 34;
*/

// V2.1_T40 T40 pin ADC synchronized pins
const int readPin = A9;
const int readPin2 = A3;
// init  adc object
ADC *adc = new ADC();
// number of sample fro averaging
int AVERAGE_SAMPLE = 5000;
// ADC init variabl
boolean WAIT = true;
// ADC waiting delay microseconds
int WAIT_DELAY_US = 100;
// ADC averaging
boolean AVERAGING_BOOL = true;

// TODO
double val = 0;

// Create the MCP9808 temperature sensor object
Adafruit_MCP9808 tempsensor = Adafruit_MCP9808();
// init temperature variable
float temperature = 0;

// V2.1_T40 LED pin
int ledPin1 = 6;
int ledPin2 = 7;

/*
 * TODO DELETE OLD 
// inint number of averaging
int AVERAGE_SAMPLE = 32;
// teensy ADC averaging init
int ADC_RESOLUTION = 13;
*/

// init sweep param
long freq_start;
long freq_stop;
long freq_step;

// init output ad8302 measurement (cast to double)
double measure_phase = 0;
double measure_mag = 0;


/*************************** FUNCTION ***************************/

/* AD9851 set frequency fucntion */
void SetFreq(long frequency)
{
  // set to 125 MHz internal clock
  temp_FTW = (frequency * pow(2, 32)) / REFCLK;
  FTW = long (temp_FTW);

  long pointer = 1;
  int pointer2 = 0b10000000;
  int lastByte = 0b10000000;

  /* 32 bit dds tuning word frequency instructions */
  for (int i = 0; i < 32; i++)
  {
    if ((FTW & pointer) > 0) digitalWrite(DATA, HIGH);
    else digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer = pointer << 1;
  }

  /* 8 bit dds phase and x6 multiplier refclock*/
  for (int i = 0; i < 8; i++)
  {
    //if ((lastByte & pointer2) > 0) digitalWrite(DATA, HIGH);
    //else digitalWrite(DATA, LOW);
    digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer2 = pointer2 >> 1;
  }

  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);

  //FTW = 0;
}

/*************************** SETUP ***************************/
void setup()
{
  // Initialise I2C communication as Master
  Wire.begin();
  // Initialise serial communication, set baud rate = 9600
  Serial.begin(115200);

  // set potentiometer value
  // Start I2C transmission
  Wire.beginTransmission(ADDRESS);
  // Send instruction for POT channel-0
  Wire.write(0x01);
  // Input resistance value, 0x80(128)
  Wire.write(POT_VALUE);
  // Stop I2C transmission
  Wire.endTransmission();

  // AD9851 set pin mode
  pinMode(WCLK, OUTPUT);
  pinMode(DATA, OUTPUT);
  pinMode(FQ_UD, OUTPUT);

  // AD9851 enter serial mode
  digitalWrite(WCLK, HIGH);
  digitalWrite(WCLK, LOW);
  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);

  /*
   * TODO DELETE OLD 
  // AD8302 set pin mode
  pinMode(AD8302_PHASE, INPUT);
  pinMode(AD8302_MAG, INPUT);
  pinMode(AD83202_REF, INPUT);
  */ 

  // V2.1_T40 T40 ADC SETTING
  pinMode(readPin, INPUT);
  pinMode(readPin2, INPUT);

  // ADC0
  adc->setAveraging(AVERAGING); // set number of averages
  adc->setResolution(RESOLUTION); // set bits of resolution
  // it can be any of the ADC_CONVERSION_SPEED enum: VERY_LOW_SPEED, LOW_SPEED, MED_SPEED, HIGH_SPEED_16BITS, HIGH_SPEED or VERY_HIGH_SPEED
  // see the documentation for more information
  // additionally the conversion speed can also be ADACK_2_4, ADACK_4_0, ADACK_5_2 and ADACK_6_2,
  // where the numbers are the frequency of the ADC clock in MHz and are independent on the bus speed.
  adc->setConversionSpeed(ADC_CONVERSION_SPEED::HIGH_SPEED); // VER 0.1.4 change the conversion speed to HIGH_SPEED 
  // it can be any of the ADC_MED_SPEED enum: VERY_LOW_SPEED, LOW_SPEED, MED_SPEED, HIGH_SPEED or VERY_HIGH_SPEED
  adc->setSamplingSpeed(ADC_SAMPLING_SPEED::HIGH_SPEED); // VER 0.1.4 change the conversion speed to HIGH_SPEED 

  // ADC1
  adc->setAveraging(AVERAGING, ADC_1); // set number of averages
  adc->setResolution(RESOLUTION, ADC_1); // set bits of resolution
  adc->setConversionSpeed(ADC_CONVERSION_SPEED::HIGH_SPEED, ADC_1); // change the conversion speed to HIGH_SPEED 
  adc->setSamplingSpeed(ADC_SAMPLING_SPEED::HIGH_SPEED, ADC_1); // change the sampling speed to HIGH_SPEED 

  adc->startSynchronizedContinuous(readPin, readPin2);

  /*
   * TODO DELETE OLD 
  // Teensy 3.6 set  adc resolution
  analogReadResolution(ADC_RESOLUTION);
  */

  // begin temperature sensor
  tempsensor.begin();

  // turn on the light
  pinMode(ledPin1, OUTPUT);
  pinMode(ledPin2, OUTPUT);
  digitalWrite(ledPin1, HIGH);
  digitalWrite(ledPin2, HIGH);
}

int message = 0;
boolean debug = true;
long pre_time = 0;
long last_time = 0;

int byteAtPort = 0;


// V2-1_T40 T40 init ADC
double value = 0;
double value2 = 0;
long time_start = 0;
ADC::Sync_result result;


/*************************** LOOP ***************************/
void loop()
{
  if ( (byteAtPort = Serial.available()) > 0) {
    // read message at serial port
    String message_str = Serial.readStringUntil('\n');
    char buf[byteAtPort];
    message_str.toCharArray(buf, sizeof(buf));
    // Firmware version query: respond and skip sweep parsing
    if (buf[0] == 'F') {
      Serial.println(FW_VERSION);
      return;
    }
    // Serial number query: read from EEPROM and respond
    if (buf[0] == 'S') {
      byte magic = EEPROM.read(ADDR_MAGIC);
      if (magic == MAGIC_BYTE) {
        byte series = EEPROM.read(ADDR_SERIES);
        uint16_t sn = ((uint16_t)EEPROM.read(ADDR_SERIAL_HIGH) << 8)
                    | EEPROM.read(ADDR_SERIAL_LOW);
        char snBuf[16];
        sprintf(snBuf, "%d-%04u", series, sn);
        Serial.println(snBuf);
      } else {
        Serial.println("NO_SERIAL");
      }
      return;
    }

    char *p = buf;
    char *str;
    int nn = 0;
    // decode message
    while ((str = strtok_r(p, ";", &p)) != NULL) { // delimiter is the semicolon
      // frequency start
      if (nn == 0) {
        freq_start = atol(str);
        // Serial.print("FREQ START = ");
        // Serial.println(freq_start);
        nn = 1;
      }
      // frequency stop
      else if (nn == 1) {
        freq_stop = atol(str);
        nn = 2;
      }
      // frequency step
      else if (nn == 2) {
        freq_step = atol(str);
        nn = 0;
        message = 1;
      }
    }

    if (message == 0) {
      // dummy do noything
    }
    if (message == 1) {
      // start sweep
      long count = 0;
      pre_time = millis();
      // start sweep cycle measurement
      for (count = freq_start; count <= freq_stop; count = count + freq_step)
      {
        // set AD9851 DDS current frequency
        SetFreq(count);
        // do the magic ! waiting for the ADC measure
        if (WAIT) delayMicroseconds(WAIT_DELAY_US);

        /*
         * TODO DELETE OLD 
        // measure gain phase
        int  app_phase = 0;
        int app_mag = 0;
        */

        // ADC measure and averaging
        if (AVERAGING == true) {

          /*
           * TODO DELETE OLD 
          for (int i = 0; i < AVERAGE_SAMPLE; i++) {
            // ADC measure phase
            app_phase += analogRead(AD8302_PHASE);
            // ADC measure gain
            app_mag += analogRead(AD8302_MAG);
          }
          // averaging (cast to double)
          measure_phase = 1.0 * app_phase / AVERAGE_SAMPLE;
          measure_mag = 1.0 * app_mag / AVERAGE_SAMPLE;

          // serial write data
          Serial.print(measure_mag);
          Serial.print(";");
          Serial.print(measure_phase);
          Serial.println();
          */

          // V2.1_T40 ADC acquisition, averaging and sending data
          value = 0;
          value2 = 0;
          for (int i = 0; i < AVERAGE_SAMPLE; i++) {
            result = adc->readSynchronizedContinuous();
            value += (uint16_t)result.result_adc0;
            value2 += (uint16_t)result.result_adc1;
          }
          // averaging (cast to double)
          value2 = 1.0 * value2 / AVERAGE_SAMPLE;
          value = 1.0 * value / AVERAGE_SAMPLE;

          // serial print data bit-amplitude and bit-phase values
          Serial.print(value*2.0);
          Serial.print(";");
          Serial.print(value2*2.0);
          Serial.println();   
        }
      }

      // measure temperature
      tempsensor.shutdown_wake(0);  // Don't remove this line! required before reading temp
      temperature = tempsensor.readTempC();
      // serial write temperature data at the end of the sweep
      Serial.print(temperature);
      Serial.print(";");
      // print termination char EOM
      Serial.println("s");
    }
  }
}
