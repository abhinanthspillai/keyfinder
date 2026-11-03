#ifndef RING_PATTERN_H
#define RING_PATTERN_H

#include <stdint.h>

// Exact replica of dashboard web audio synthesizer:
// 1400ms cycle: [3 short 75ms chirps] [165ms pause] [3 short 75ms chirps] [605ms pause]
class RingPattern {
public:
    static const uint32_t CYCLE_PERIOD_MS = 1400;
    static const uint32_t TOTAL_DURATION_MS = 4000; // Exactly 4 seconds duration

    RingPattern();

    // Start playing the pattern
    void start();

    // Stop playing immediately
    void stop();

    // Update state based on current time (millis)
    // Returns true when buzzer should be ON (GPIO HIGH), false when OFF (GPIO LOW)
    bool update(uint32_t currentTime);

    // Whether pattern is currently playing
    bool isPlaying() const;

    // Whether pattern has completed
    bool isComplete() const;

private:
    volatile bool playing;
    volatile uint32_t startTime;
};

#endif // RING_PATTERN_H
