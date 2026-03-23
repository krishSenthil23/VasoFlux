#include <LiquidCrystal.h>

LiquidCrystal lcd(2, 3, 4, 5, 6, 8);

// --- Pins ---
const int BUTTON1_PIN = 9;
const int BUTTON2_PIN = 10;
const int GREEN_LED   = 12;
const int RED_LED     = 11;
const int BUZZER_PIN  = 7;

// --- Note frequencies ---
#define C4  262
#define D4  294
#define E4  330
#define F4  349
#define G4  392
#define A4  440
#define B4  494
#define C5  523
#define D5  587
#define E5  659
#define F5  698
#define G5  784
#define A5  880
#define REST 0

// --- Unhealthy demo preset ---
const float CO2_UNHEALTHY = 46.0;
const float O2_UNHEALTHY  = 19.0;

// --- Risk thresholds ---
const float CO2_RISK = 45.0;
const float O2_RISK  = 19.5;

// --- Mock saved data (last 5 days) ---
const char* savedDates[]  = { "Mar 15", "Mar 16", "Mar 17", "Mar 18", "Mar 19" };
const float savedCO2[]    = { 42.1, 43.8, 44.5, 45.9, 46.0 };
const float savedO2[]     = { 20.8, 20.4, 20.1, 19.6, 19.0 };

// --- States ---
#define STATE_IDLE      0
#define STATE_COUNTDOWN 1
#define STATE_RESULTS   2
#define STATE_BLINK     3
#define STATE_HISTORY   4

int state        = STATE_IDLE;
int resultScreen = 0;
const int TOTAL_RESULT_SCREENS = 3;

// --- History browsing ---
int historyScreen = 0;
// Total history screens:
// 0        = title screen
// 1–5      = one per saved day (5 days)
// 6        = average summary
// 7        = trend analysis
// 8        = pattern warning
const int TOTAL_HISTORY_SCREENS = 9;

// --- Active demo ---
float currentCO2;
float currentO2;
int   activeLED;

// --- Countdown ---
const int COUNTDOWN_SECONDS  = 5;
unsigned long countdownStart = 0;
int lastSecondsDisplayed     = -1;

// --- LCD scanning animation ---
int  scanPos     = 0;
bool scanDir     = true;
unsigned long lastScanTime = 0;
const unsigned long SCAN_SPEED = 120;

// --- LCD blink ---
bool blinkVisible           = true;
unsigned long lastBlinkTime = 0;
const unsigned long BLINK_DELAY = 500;

// --- Button debounce ---
bool btn1Pressed = false, btn2Pressed = false;
bool lastBtn1    = HIGH,  lastBtn2    = HIGH;
unsigned long lastDeb1 = 0, lastDeb2 = 0;
const unsigned long DEB = 50;

// --- LED pattern engine ---
const unsigned long PAT_SCAN_PULSE[] = { 150, 150, 0 };
const unsigned long PAT_ATRISK[]     = { 100, 100, 0 };
const unsigned long PAT_ALERT[]      = { 60,  60,  0 };
const unsigned long PAT_HISTORY[]    = { 300, 700, 0 };  // slow pulse for history mode

const unsigned long* ledPattern = nullptr;
int           patStep   = 0;
bool          ledOn     = false;
unsigned long lastLedTime = 0;

void setPattern(const unsigned long* pattern) {
    ledPattern  = pattern;
    patStep     = 0;
    ledOn       = true;
    lastLedTime = millis();
    digitalWrite(RED_LED,   LOW);
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(activeLED, HIGH);
}

void updateLED() {
    if (!ledPattern) return;
    if (ledPattern[patStep] == 0) patStep = 0;
    if (millis() - lastLedTime >= ledPattern[patStep]) {
        lastLedTime = millis();
        patStep++;
        if (ledPattern[patStep] == 0) patStep = 0;
        ledOn = !ledOn;
        digitalWrite(activeLED, ledOn ? HIGH : LOW);
    }
}

void stopLEDs() {
    ledPattern = nullptr;
    patStep    = 0;
    ledOn      = false;
    digitalWrite(RED_LED,   LOW);
    digitalWrite(GREEN_LED, LOW);
}

// -------------------------------------------------------
// --- Buzzer ---
// -------------------------------------------------------

void playNote(int freq, int dur) {
    if (freq == REST) noTone(BUZZER_PIN);
    else              tone(BUZZER_PIN, freq, dur);
    delay(dur + 20);
}

void playLoseSound() {
    playNote(E5,  120);
    playNote(D5,  120);
    playNote(C5,  120);
    playNote(B4,  120);
    playNote(REST, 80);
    playNote(B4,  100);
    playNote(A4,  100);
    playNote(G4,  400);
    noTone(BUZZER_PIN);
}

// Short 2-note blip when browsing history
void playHistoryBlip() {
    tone(BUZZER_PIN, C5, 40);
    delay(60);
    noTone(BUZZER_PIN);
}

// Warning tone when trend is bad
void playTrendWarning() {
    playNote(G4, 100);
    playNote(REST, 40);
    playNote(G4, 100);
    playNote(REST, 40);
    playNote(E4, 300);
    noTone(BUZZER_PIN);
}

// -------------------------------------------------------

bool co2Risk()  { return currentCO2 > CO2_RISK; }
bool o2Risk()   { return currentO2  < O2_RISK;  }
bool isAtRisk() { return co2Risk()  || o2Risk(); }

// -------------------------------------------------------
// --- History screens ---
// -------------------------------------------------------

void showHistoryScreen(int screen) {
    lcd.clear();

    if (screen == 0) {
        // Title
        lcd.setCursor(0, 0);
        lcd.print("Saved Data");
        lcd.setCursor(0, 1);
        lcd.print("Last 5 days >");
        return;
    }

    if (screen >= 1 && screen <= 5) {
        // One day per screen
        int i = screen - 1;
        lcd.setCursor(0, 0);
        lcd.print(savedDates[i]);
        lcd.print(" ");
        // Show if that day was at risk
        bool dayRisk = savedCO2[i] > CO2_RISK || savedO2[i] < O2_RISK;
        lcd.print(dayRisk ? "!" : "OK");
        lcd.setCursor(0, 1);
        lcd.print("CO2:");
        lcd.print(savedCO2[i], 1);
        lcd.print(" O2:");
        lcd.print(savedO2[i], 1);
        return;
    }

    if (screen == 6) {
        // Average summary
        float avgCO2 = 0, avgO2 = 0;
        for (int i = 0; i < 5; i++) { avgCO2 += savedCO2[i]; avgO2 += savedO2[i]; }
        avgCO2 /= 5; avgO2 /= 5;
        lcd.setCursor(0, 0);
        lcd.print("5-Day Average:");
        lcd.setCursor(0, 1);
        lcd.print("CO2:");
        lcd.print(avgCO2, 1);
        lcd.print(" O2:");
        lcd.print(avgO2, 1);
        return;
    }

    if (screen == 7) {
        // Trend direction
        float co2Change = savedCO2[4] - savedCO2[0];
        float o2Change  = savedO2[4]  - savedO2[0];
        lcd.setCursor(0, 0);
        lcd.print("5-Day Trend:");
        lcd.setCursor(0, 1);
        lcd.print("CO2 ");
        lcd.print(co2Change > 0 ? "+" : "");
        lcd.print(co2Change, 1);
        lcd.print(" O2 ");
        lcd.print(o2Change > 0 ? "+" : "");
        lcd.print(o2Change, 1);
        return;
    }

    if (screen == 8) {
        // Pattern warning
        float co2Change = savedCO2[4] - savedCO2[0];
        lcd.setCursor(0, 0);
        if (co2Change > 3.0) {
            lcd.print("TREND: Rising");
            lcd.setCursor(0, 1);
            lcd.print("See Dr. Rivera");
        } else if (co2Change > 1.0) {
            lcd.print("TREND: Elevated");
            lcd.setCursor(0, 1);
            lcd.print("Monitor closely");
        } else {
            lcd.print("TREND: Stable");
            lcd.setCursor(0, 1);
            lcd.print("Levels look OK");
        }
        return;
    }
}

// -------------------------------------------------------

void startupAnimation() {
    lcd.clear();

    int notes[]     = { C4, E4, G4, C5, REST, G4, A4, G4, E4, REST, C4, E4, G4, C5 };
    int durations[] = { 80, 80, 80, 160, 60, 80, 80, 80, 160, 60, 80, 80, 80, 300 };
    int noteIndex   = 0;

    for (int i = 0; i < 16; i++) {
        lcd.setCursor(i, 0); lcd.write(0xFF);
        lcd.setCursor(i, 1); lcd.write(0xFF);
        digitalWrite(GREEN_LED, i % 2 == 0 ? HIGH : LOW);
        digitalWrite(RED_LED,   i % 2 == 0 ? LOW  : HIGH);
        if (noteIndex < 14) {
            if (notes[noteIndex] == REST) noTone(BUZZER_PIN);
            else tone(BUZZER_PIN, notes[noteIndex]);
            noteIndex++;
        }
        delay(60);
    }
    delay(200);

    for (int i = 15; i >= 0; i--) {
        lcd.setCursor(i, 0); lcd.print(" ");
        lcd.setCursor(i, 1); lcd.print(" ");
        digitalWrite(GREEN_LED, i % 2 == 0 ? HIGH : LOW);
        digitalWrite(RED_LED,   i % 2 == 0 ? LOW  : HIGH);
        delay(60);
    }
    noTone(BUZZER_PIN);
    stopLEDs();
    delay(150);

    for (int f = 0; f < 2; f++) {
        for (int i = 0; i < 16; i++) {
            lcd.setCursor(i, 0); lcd.write(0xFF);
            lcd.setCursor(i, 1); lcd.write(0xFF);
        }
        digitalWrite(GREEN_LED, HIGH);
        digitalWrite(RED_LED,   HIGH);
        tone(BUZZER_PIN, f == 0 ? G5 : C5, 140);
        delay(150);
        lcd.clear();
        digitalWrite(GREEN_LED, LOW);
        digitalWrite(RED_LED,   LOW);
        noTone(BUZZER_PIN);
        delay(100);
    }
    delay(200);
}

void showIdle() {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Btn1: Scan");
    lcd.setCursor(0, 1);
    lcd.print("Btn2: History");
}

void initScanDisplay(int s) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Scanning: ");
    lcd.print(s);
    lcd.print("s  ");
    scanPos      = 0;
    scanDir      = true;
    lastScanTime = millis();
    lcd.setCursor(0, 1);
    for (int i = 0; i < 16; i++) lcd.print(i == 0 ? char(0xFF) : ' ');
}

void updateScanAnimation() {
    if (millis() - lastScanTime < SCAN_SPEED) return;
    lastScanTime = millis();
    lcd.setCursor(0, 1);
    for (int i = 0; i < 16; i++) {
        lcd.print(i == scanPos ? char(0xFF) : ' ');
    }
    if (scanDir) { scanPos++; if (scanPos >= 15) scanDir = false; }
    else         { scanPos--; if (scanPos <= 0)  scanDir = true;  }
}

void updateScanTimer(int s) {
    lcd.setCursor(10, 0);
    lcd.print(s);
    lcd.print("s  ");
}

void showResult(int screen) {
    lcd.clear();
    switch (screen) {
        case 0:
            lcd.setCursor(0, 0);
            lcd.print("CO2:");
            lcd.print(currentCO2, 1);
            lcd.print(" mmHg");
            lcd.setCursor(0, 1);
            lcd.print("O2: ");
            lcd.print(currentO2, 1);
            lcd.print("%");
            break;
        case 1:
            lcd.setCursor(0, 0);
            lcd.print("CO2: ");
            lcd.print(co2Risk() ? "HIGH" : "OK");
            lcd.setCursor(0, 1);
            lcd.print("O2:  ");
            lcd.print(o2Risk()  ? "LOW"  : "OK");
            break;
        case 2:
            lcd.setCursor(0, 0);
            lcd.print("Hypercapnia:");
            lcd.setCursor(0, 1);
            lcd.print(isAtRisk() ? "AT RISK!" : "No Risk");
            break;
    }
}

void showBlinkFrame(bool visible) {
    lcd.setCursor(0, 0);
    lcd.print(visible ? "!! AT RISK !!   " : "                ");
    lcd.setCursor(0, 1);
    lcd.print(visible ? "Hypercapnia     " : "                ");
}

// -------------------------------------------------------

void startDemo(float co2, float o2, int led) {
    currentCO2           = co2;
    currentO2            = o2;
    activeLED            = led;
    state                = STATE_COUNTDOWN;
    countdownStart       = millis();
    lastSecondsDisplayed = COUNTDOWN_SECONDS;
    initScanDisplay(COUNTDOWN_SECONDS);
    setPattern(PAT_SCAN_PULSE);
}

void setup() {
    delay(1000);
    lcd.begin(16, 2);
    delay(500);

    pinMode(BUTTON1_PIN, INPUT_PULLUP);
    pinMode(BUTTON2_PIN, INPUT_PULLUP);
    pinMode(GREEN_LED,   OUTPUT);
    pinMode(RED_LED,     OUTPUT);
    pinMode(BUZZER_PIN,  OUTPUT);

    digitalWrite(GREEN_LED, LOW);
    digitalWrite(RED_LED,   LOW);

    startupAnimation();
    showIdle();
}

void loop() {
    // --- Debounce button 1 ---
    bool r1 = digitalRead(BUTTON1_PIN);
    if (r1 != lastBtn1) lastDeb1 = millis();
    bool b1 = false;
    if (millis() - lastDeb1 > DEB) {
        if (r1 == LOW && !btn1Pressed) { btn1Pressed = true; b1 = true; }
        if (r1 == HIGH)                  btn1Pressed = false;
    }
    lastBtn1 = r1;

    // --- Debounce button 2 ---
    bool r2 = digitalRead(BUTTON2_PIN);
    if (r2 != lastBtn2) lastDeb2 = millis();
    bool b2 = false;
    if (millis() - lastDeb2 > DEB) {
        if (r2 == LOW && !btn2Pressed) { btn2Pressed = true; b2 = true; }
        if (r2 == HIGH)                  btn2Pressed = false;
    }
    lastBtn2 = r2;

    // --- LED tick ---
    updateLED();

    // --- State machine ---
    switch (state) {

        case STATE_IDLE:
            // Button 1 = run scan
            if (b1) startDemo(CO2_UNHEALTHY, O2_UNHEALTHY, RED_LED);
            // Button 2 = view saved history
            if (b2) {
                state         = STATE_HISTORY;
                historyScreen = 0;
                activeLED     = GREEN_LED;
                setPattern(PAT_HISTORY);
                showHistoryScreen(0);
            }
            break;

        case STATE_COUNTDOWN: {
            int s = COUNTDOWN_SECONDS - (int)((millis() - countdownStart) / 1000);
            if (s <= 0) {
                state        = STATE_RESULTS;
                resultScreen = 0;
                setPattern(PAT_ATRISK);
                showResult(0);
            } else {
                if (s != lastSecondsDisplayed) {
                    lastSecondsDisplayed = s;
                    updateScanTimer(s);
                }
                updateScanAnimation();
            }
            break;
        }

        case STATE_RESULTS:
            if (b1 || b2) {
                resultScreen++;
                if (resultScreen >= TOTAL_RESULT_SCREENS) {
                    stopLEDs();
                    noTone(BUZZER_PIN);
                    showIdle();
                    state = STATE_IDLE;
                } else if (resultScreen == 2 && isAtRisk()) {
                    state         = STATE_BLINK;
                    blinkVisible  = true;
                    lastBlinkTime = millis();
                    setPattern(PAT_ALERT);
                    showBlinkFrame(true);
                    playLoseSound();
                } else {
                    showResult(resultScreen);
                }
            }
            break;

        case STATE_BLINK:
            if (millis() - lastBlinkTime >= BLINK_DELAY) {
                lastBlinkTime = millis();
                blinkVisible  = !blinkVisible;
                showBlinkFrame(blinkVisible);
            }
            if (b1 || b2) {
                stopLEDs();
                noTone(BUZZER_PIN);
                showIdle();
                state = STATE_IDLE;
            }
            break;

        case STATE_HISTORY:
            if (b2) {
                // Button 2 advances through history screens
                historyScreen++;
                if (historyScreen >= TOTAL_HISTORY_SCREENS) {
                    // End of history — back to idle
                    stopLEDs();
                    showIdle();
                    state = STATE_IDLE;
                } else {
                    playHistoryBlip();
                    // Play warning tone on the trend/pattern screen if rising
                    if (historyScreen == 8) {
                        float co2Change = savedCO2[4] - savedCO2[0];
                        if (co2Change > 1.0) playTrendWarning();
                    }
                    showHistoryScreen(historyScreen);
                }
            }
            // Button 1 exits history early
            if (b1) {
                stopLEDs();
                noTone(BUZZER_PIN);
                showIdle();
                state = STATE_IDLE;
            }
            break;
    }
}