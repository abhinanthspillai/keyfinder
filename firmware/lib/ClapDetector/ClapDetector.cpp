#include "ClapDetector.h"
#ifdef ARDUINO
#include <Arduino.h>
#endif

ClapDetector::ClapDetector(
    uint16_t debounce,
    uint16_t minGap,
    uint16_t maxGap,
    uint16_t maxPulse,
    uint16_t noiseCheck,
    uint16_t postRing
) : debounceMs(debounce),
    minGapMs(minGap),
    maxGapMs(maxGap),
    maxPulseMs(maxPulse),
    noiseCheckMs(noiseCheck),
    postRingSilenceMs(postRing),
    state(IDLE),
    firstClapTime(0),
    lastActiveTime(0),
    cooldownStartTime(0),
    pulseStartTime(0),
    pulseWasActive(false),
    clapCount(0) {
}

void ClapDetector::reset() {
    state = IDLE;
    firstClapTime = 0;
    lastActiveTime = 0;
    clapCount = 0;
    pulseWasActive = false;
}

bool ClapDetector::isInCooldown(uint32_t currentTime) const {
    if (state == COOLDOWN) {
        return (currentTime - cooldownStartTime) < postRingSilenceMs;
    }
    return false;
}

bool ClapDetector::processSound(uint32_t currentTime, bool soundActive, bool isRinging) {
    // If ringing, ignore all sound and enter cooldown
    if (isRinging) {
        if (state != COOLDOWN) {
            state = COOLDOWN;
            cooldownStartTime = currentTime;
        }
        return false;
    }

    // Check cooldown
    if (state == COOLDOWN) {
        if (currentTime - cooldownStartTime >= postRingSilenceMs) {
            state = IDLE;
        } else {
            return false;
        }
    }

    // Debounce: ignore if too soon after last active
    if (currentTime - lastActiveTime < debounceMs) {
        return false;
    }

    // Detect rising or falling edge of sound pulse
    bool edgeDetected = (soundActive != pulseWasActive);
    pulseWasActive = soundActive;

    if (!edgeDetected) {
        return false;
    }

    if (soundActive) {
        // Sound just became active - start pulse timing
        pulseStartTime = currentTime;
        lastActiveTime = currentTime;
        return false;
    } else {
        // Sound just became inactive - check pulse length
        uint32_t pulseDuration = currentTime - pulseStartTime;
        lastActiveTime = currentTime;

        // If pulse is too long, treat as noise and reset
        if (pulseDuration > maxPulseMs) {
            reset();
            return false;
        }

        // Valid short pulse detected - this is a clap
        clapCount++;

        if (state == IDLE) {
            // First clap
            state = FIRST_CLAP_DETECTED;
            firstClapTime = currentTime;
#ifdef ARDUINO
            Serial.printf("[CLAP] First clap detected (duration=%lu ms). Waiting for 2nd clap...\n", (unsigned long)pulseDuration);
#endif
            return false;
        } else if (state == FIRST_CLAP_DETECTED) {
            // Check if within valid gap for second clap
            uint32_t gap = currentTime - firstClapTime;

            if (gap >= minGapMs && gap <= maxGapMs) {
                // Valid double clap!
#ifdef ARDUINO
                Serial.printf("[CLAP] Second clap detected! (gap=%lu ms) -> TRIGGERING RING!\n", (unsigned long)gap);
#endif
                state = COOLDOWN;
                cooldownStartTime = currentTime;
                reset();
                return true;
            } else if (gap > maxGapMs) {
                // Gap too long - reset and count this as first clap
#ifdef ARDUINO
                Serial.printf("[CLAP] Gap too long (%lu ms > %u ms). Resetting as first clap.\n", (unsigned long)gap, (unsigned int)maxGapMs);
#endif
                firstClapTime = currentTime;
                clapCount = 1;
                return false;
            } else {
                // Gap too short - noise, reset
#ifdef ARDUINO
                Serial.printf("[CLAP] Gap too short (%lu ms < %u ms). Noise ignored.\n", (unsigned long)gap, (unsigned int)minGapMs);
#endif
                reset();
                return false;
            }
        }
    }

    return false;
}
