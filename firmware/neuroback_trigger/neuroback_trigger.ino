// NeuroBack trigger firmware (Arduino Uno / Mega / Nano).
//
// Serial protocol at 115200 baud, one byte per command:
//   'F'  one LED pulse of PULSE_US microseconds (non-blocking)
//   'p'  LED on   (2023 protocol, kept for compatibility)
//   'a'  LED off  (2023 protocol)
//   '?'  replies "NEUROBACK-TRIGGER 2.0"
//
// TRIGGER_OUT mirrors every pulse as a TTL edge you can wire to an OpenBCI Cyton digital
// input (D11/D12/D17 in digital-read mode) so flash times land on the EEG clock.
// See docs/hardware.md for wiring, LED current limits and the photodiode latency test.

const uint8_t LED_PIN = 9;        // LED via a 220-470 ohm resistor (or a MOSFET for a high-power LED)
const uint8_t TRIGGER_OUT = 7;    // optional TTL marker for the Cyton
const unsigned long PULSE_US = 20000UL;  // 20 ms, about a fifth of an alpha cycle

unsigned long pulseStart = 0;
bool pulsing = false;

void setup() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(TRIGGER_OUT, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(TRIGGER_OUT, LOW);
  Serial.begin(115200);
}

void setOutputs(bool on) {
  digitalWrite(LED_PIN, on ? HIGH : LOW);
  digitalWrite(TRIGGER_OUT, on ? HIGH : LOW);
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'F') {
      setOutputs(true);
      pulseStart = micros();
      pulsing = true;
    } else if (c == 'p') {
      setOutputs(true);
      pulsing = false;
    } else if (c == 'a') {
      setOutputs(false);
      pulsing = false;
    } else if (c == '?') {
      Serial.println("NEUROBACK-TRIGGER 2.0");
    }
  }
  if (pulsing && (micros() - pulseStart) >= PULSE_US) {
    setOutputs(false);
    pulsing = false;
  }
}
