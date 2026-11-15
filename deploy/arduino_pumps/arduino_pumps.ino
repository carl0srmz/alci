// ALCI pump relays on an Arduino Uno. Serial 9600, one command per line:
//   "A 0|1"  relay board active level (0 = HIGH turns the relay on, 1 = LOW turns it on)
//   "P1 <s>" / "P2 <s>"  run pump 1/2 for <s> seconds (0 = stop now)
// Each run stops itself, so a crashed Pi can't leave a pump running.
const byte PIN[2] = {7, 8};
bool activeLow = true;  // this relay board turns on with a LOW pin
unsigned long stopAt[2] = {0, 0};
bool running[2] = {false, false};

void drive(int i, bool on) {
  running[i] = on;
  digitalWrite(PIN[i], on != activeLow ? HIGH : LOW);  // on+high-active or off+low-active -> HIGH
}

void setup() {
  Serial.begin(9600);
  for (int i = 0; i < 2; i++) { pinMode(PIN[i], OUTPUT); drive(i, false); }
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("A ")) {
      activeLow = line.substring(2).toInt() != 0;
      for (int i = 0; i < 2; i++) drive(i, running[i]);
    } else if (line.length() > 3 && line[0] == 'P' && (line[1] == '1' || line[1] == '2')) {
      int i = line[1] - '1';
      long s = line.substring(3).toInt();
      if (s > 0) { stopAt[i] = millis() + (unsigned long)s * 1000UL; drive(i, true); }
      else drive(i, false);
      Serial.println("ok");
    }
  }
  for (int i = 0; i < 2; i++)
    if (running[i] && (long)(millis() - stopAt[i]) >= 0) drive(i, false);
}
