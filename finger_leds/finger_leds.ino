const uint8_t LED_PINS[5] = {2, 3, 4, 5, 6};   // thumb, index, middle, ring, pinky
const unsigned long TIMEOUT_MS = 1500;
unsigned long lastRx = 0;

void applyMask(uint8_t mask) {
  for (uint8_t i = 0; i < 5; i++) {
    digitalWrite(LED_PINS[i], (mask >> i) & 0x01);
  }
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < 5; i++) pinMode(LED_PINS[i], OUTPUT);
  applyMask(0);

  // startup chase to confirm wiring
  for (uint8_t i = 0; i < 5; i++) {
    digitalWrite(LED_PINS[i], HIGH);
    delay(120);
    digitalWrite(LED_PINS[i], LOW);
  }
}

void loop() {
  while (Serial.available() > 0) {
    uint8_t mask = Serial.read();
    applyMask(mask & 0x1F);
    lastRx = millis();
  }
  if (millis() - lastRx > TIMEOUT_MS) applyMask(0);   // failsafe
}