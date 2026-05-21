/* LICENSE
 * Copyright (C) 2014 openQCM
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see http://www.gnu.org/licenses/gpl-3.0.txt
 *
 * INTRO
 * Program for storing the openQCM Q-1 serial number in Teensy EEPROM memory.
 * Compatible with Teensy 3.6 and Teensy 4.0.
 *
 * EEPROM LAYOUT (4 bytes)
 *   Address 0: MAGIC byte (0xA5) — flags that the serial has been programmed
 *   Address 1: SERIES      — production batch number (0–255)
 *   Address 2: SERIAL HIGH — serial number high byte
 *   Address 3: SERIAL LOW  — serial number low byte
 *
 * The serial number is displayed as SERIES-NNNN (e.g. 19-0055).
 *
 * ANTI-OVERWRITE PROTECTION
 *   If the EEPROM already contains a valid serial number (magic byte present),
 *   the programmer will NOT overwrite it automatically. The operator must send
 *   'Y' via Serial Monitor to confirm the overwrite.
 *
 * USAGE
 *   1. Set OPENQCM_SERIES and OPENQCM_SERIAL below
 *   2. Flash this sketch to the Teensy
 *   3. Open Serial Monitor (115200 baud)
 *   4. Verify the serial number is correct
 *   5. Flash the operational firmware (EEPROM is preserved)
 *
 * author     Marco Mauro
 * version    2.0
 * date       May 2026
 */

#include <EEPROM.h>

/*************************** EEPROM LAYOUT ***************************/
#define ADDR_MAGIC        0
#define ADDR_SERIES       1
#define ADDR_SERIAL_HIGH  2
#define ADDR_SERIAL_LOW   3

#define MAGIC_BYTE  0xA5

/*************** CONFIGURE THESE BEFORE EACH BOARD *******************/
#define OPENQCM_SERIES   19      // Production batch (0–255)
#define OPENQCM_SERIAL   55      // Board serial number (0–65535)
/*********************************************************************/

bool waitingConfirmation = false;
bool programmingDone = false;

/* Write the configured serial number into EEPROM */
void writeSerialNumber() {
  EEPROM.write(ADDR_MAGIC, MAGIC_BYTE);
  EEPROM.write(ADDR_SERIES, (byte)OPENQCM_SERIES);
  EEPROM.write(ADDR_SERIAL_HIGH, (OPENQCM_SERIAL >> 8) & 0xFF);
  EEPROM.write(ADDR_SERIAL_LOW, OPENQCM_SERIAL & 0xFF);
}

/* Read and print the serial number stored in EEPROM */
void printStoredSerial() {
  byte magic = EEPROM.read(ADDR_MAGIC);
  if (magic != MAGIC_BYTE) {
    Serial.println("  (no serial number programmed)");
    return;
  }
  byte series = EEPROM.read(ADDR_SERIES);
  uint16_t serial = ((uint16_t)EEPROM.read(ADDR_SERIAL_HIGH) << 8)
                  | EEPROM.read(ADDR_SERIAL_LOW);
  char buf[16];
  sprintf(buf, "  %d-%04u", series, serial);
  Serial.println(buf);
}

/* Print the value that will be written (from #defines) */
void printNewSerial() {
  char buf[16];
  sprintf(buf, "  %d-%04u", OPENQCM_SERIES, OPENQCM_SERIAL);
  Serial.println(buf);
}

void setup() {
  Serial.begin(115200);
  delay(2000);  // wait for Serial Monitor to connect

  Serial.println("========================================");
  Serial.println("  openQCM Q-1 Serial Number Programmer");
  Serial.println("========================================");
  Serial.println();

  byte magic = EEPROM.read(ADDR_MAGIC);

  if (magic == MAGIC_BYTE) {
    // A serial number already exists — anti-overwrite protection
    Serial.println("WARNING: this board already has a serial number!");
    Serial.println();
    Serial.println("Existing serial:");
    printStoredSerial();
    Serial.println();
    Serial.println("New serial to program:");
    printNewSerial();
    Serial.println();
    Serial.println("Send 'Y' to overwrite, any other key to abort.");
    waitingConfirmation = true;
  } else {
    // Virgin EEPROM — program directly
    Serial.println("No existing serial number found. Programming...");
    Serial.println();
    writeSerialNumber();
    programmingDone = true;
    Serial.println("Done! Serial number programmed:");
    printStoredSerial();
    Serial.println();
    Serial.println("Verify the number above, then flash the operational firmware.");
  }
}

void loop() {
  // Handle overwrite confirmation
  if (waitingConfirmation && Serial.available() > 0) {
    char c = Serial.read();
    // Drain any remaining characters (e.g. \r\n from Serial Monitor)
    while (Serial.available() > 0) Serial.read();

    if (c == 'Y' || c == 'y') {
      Serial.println();
      Serial.println("Overwriting serial number...");
      Serial.println();
      writeSerialNumber();
      programmingDone = true;
      Serial.println("Done! New serial number programmed:");
      printStoredSerial();
      Serial.println();
      Serial.println("Verify the number above, then flash the operational firmware.");
    } else {
      Serial.println();
      Serial.println("Aborted. Existing serial number preserved:");
      printStoredSerial();
      programmingDone = true;
    }
    waitingConfirmation = false;
  }

  // Periodic verification printout after programming
  if (programmingDone) {
    delay(3000);
    Serial.print("SERIALNUMBER = ");
    byte series = EEPROM.read(ADDR_SERIES);
    uint16_t serial = ((uint16_t)EEPROM.read(ADDR_SERIAL_HIGH) << 8)
                    | EEPROM.read(ADDR_SERIAL_LOW);
    char buf[16];
    sprintf(buf, "%d-%04u", series, serial);
    Serial.println(buf);
  }
}
