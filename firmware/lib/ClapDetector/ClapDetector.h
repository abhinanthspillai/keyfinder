#ifndef CLAP_DETECTOR_H
#define CLAP_DETECTOR_H

#include <stdint.h>

// Pure logic clap detection - no Arduino calls, testable on host
class ClapDetector {
public:
    // Timing configuration (milliseconds)
    uint16_t debounceMs;
    uint16_t minGapMs;
    uint16_t maxGapMs;
    uint16_t maxPulseMs;
    uint16_t noiseCheckMs;
    uint16_t postRingSilenceMs;

    ClapDetector(
        uint16_t debounce = 80,
        uint16_t minGap = 150,
        uint16_t maxGap = 900,
        uint16_t maxPulse = 400,
        uint16_t noiseCheck = 250,
        uint16_t postRing = 2000
    );

    // Process a sound pulse. Returns true if valid double clap detected.
    // Parameters:
    //   currentTime: current time in milliseconds
    //   soundActive: true if sound is currently active (pin state)
    //   isRinging: true if ring pattern is currently playing
    bool processSound(uint32_t currentTime, bool soundActive, bool isRinging);

    // Reset state (call after successful double clap or on manual reset)
    void reset();

    // Check if in cooldown period (ignore sound during/after ring)
    bool isInCooldown(uint32_t currentTime) const;

private:
    enum State {
        IDLE,
        FIRST_CLAP_DETECTED,
        WAITING_SECOND_CLAP,
        COOLDOWN
    };

    State state;
    uint32_t firstClapTime;
    uint32_t lastActiveTime;
    uint32_t cooldownStartTime;
    uint32_t pulseStartTime;
    bool pulseWasActive;
    int clapCount;
};

#endif // CLAP_DETECTOR_H
