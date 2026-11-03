#include "RingPattern.h"
#include <Arduino.h>

RingPattern::RingPattern() : playing(false), startTime(0) {}

void RingPattern::start() {
    startTime = millis();
    playing = true;
}

void RingPattern::stop() {
    playing = false;
    startTime = 0;
}

bool RingPattern::isPlaying() const {
    return playing;
}

bool RingPattern::isComplete() const {
    return !playing;
}

bool RingPattern::update(uint32_t currentTime) {
    if (!playing) {
        return false;
    }

    if (startTime == 0) {
        startTime = currentTime;
    }

    uint32_t elapsed = currentTime - startTime;

    if (elapsed >= TOTAL_DURATION_MS) {
        stop();
        return false;
    }

    // Exact replica of dashboard web audio synthesizer:
    // Cycle = 1400ms
    // Chirp 1: 0 - 75ms ON
    // Gap: 75 - 120ms OFF
    // Chirp 2: 120 - 195ms ON
    // Gap: 195 - 240ms OFF
    // Chirp 3: 240 - 315ms ON
    // Burst pause: 315 - 480ms OFF
    // Chirp 4: 480 - 555ms ON
    // Gap: 555 - 600ms OFF
    // Chirp 5: 600 - 675ms ON
    // Gap: 675 - 720ms OFF
    // Chirp 6: 720 - 795ms ON
    // Cycle pause: 795 - 1400ms OFF
    uint32_t cycleTime = elapsed % CYCLE_PERIOD_MS;

    if (cycleTime < 75) {
        return true;
    } else if (cycleTime < 120) {
        return false;
    } else if (cycleTime < 195) {
        return true;
    } else if (cycleTime < 240) {
        return false;
    } else if (cycleTime < 315) {
        return true;
    } else if (cycleTime < 480) {
        return false;
    } else if (cycleTime < 555) {
        return true;
    } else if (cycleTime < 600) {
        return false;
    } else if (cycleTime < 675) {
        return true;
    } else if (cycleTime < 720) {
        return false;
    } else if (cycleTime < 795) {
        return true;
    } else {
        return false;
    }
}
