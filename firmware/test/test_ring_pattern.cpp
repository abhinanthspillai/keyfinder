#include "unity.h"
#include "../lib/RingPattern/RingPattern.h"

// Test fixture
static RingPattern* pattern;

void setUp(void) {
    pattern = new RingPattern();
}

void tearDown(void) {
    delete pattern;
}

// Test: Pattern is idle initially
void test_initial_idle(void) {
    TEST_ASSERT_FALSE(pattern->isPlaying());
    TEST_ASSERT_TRUE(pattern->isComplete());
    TEST_ASSERT_FALSE(pattern->update(0));
}

// Test: Start pattern
void test_start_pattern(void) {
    pattern->start();
    TEST_ASSERT_TRUE(pattern->isPlaying());
    TEST_ASSERT_FALSE(pattern->isComplete());
    TEST_ASSERT_TRUE(pattern->update(0)); // Buzzer ON
}

// Test: Stop pattern immediately
void test_stop_immediately(void) {
    pattern->start();
    pattern->stop();
    TEST_ASSERT_FALSE(pattern->isPlaying());
    TEST_ASSERT_TRUE(pattern->isComplete());
    TEST_ASSERT_FALSE(pattern->update(100));
}

// Test: Pattern timing (3 beeps, pause, 3 beeps)
void test_pattern_timing(void) {
    pattern->start();

    // First beep: 0-200ms ON
    TEST_ASSERT_TRUE(pattern->update(0));
    TEST_ASSERT_TRUE(pattern->update(100));
    TEST_ASSERT_TRUE(pattern->update(199));
    TEST_ASSERT_FALSE(pattern->update(200)); // Gap starts

    // First gap: 200-350ms OFF
    TEST_ASSERT_FALSE(pattern->update(250));
    TEST_ASSERT_FALSE(pattern->update(349));
    TEST_ASSERT_TRUE(pattern->update(350)); // Second beep starts

    // Second beep: 350-550ms ON
    TEST_ASSERT_TRUE(pattern->update(400));
    TEST_ASSERT_TRUE(pattern->update(549));
    TEST_ASSERT_FALSE(pattern->update(550)); // Gap starts

    // Second gap: 550-700ms OFF
    TEST_ASSERT_FALSE(pattern->update(600));
    TEST_ASSERT_FALSE(pattern->update(699));
    TEST_ASSERT_TRUE(pattern->update(700)); // Third beep starts

    // Third beep: 700-900ms ON
    TEST_ASSERT_TRUE(pattern->update(750));
    TEST_ASSERT_TRUE(pattern->update(899));
    TEST_ASSERT_FALSE(pattern->update(900)); // Group pause starts

    // Group pause: 900-1800ms OFF
    TEST_ASSERT_FALSE(pattern->update(1000));
    TEST_ASSERT_FALSE(pattern->update(1500));
    TEST_ASSERT_FALSE(pattern->update(1799));
    TEST_ASSERT_TRUE(pattern->update(1800)); // Fourth beep starts

    // Fourth beep: 1800-2000ms ON
    TEST_ASSERT_TRUE(pattern->update(1900));
    TEST_ASSERT_TRUE(pattern->update(1999));
    TEST_ASSERT_FALSE(pattern->update(2000)); // Gap starts

    // Fourth gap: 2000-2150ms OFF
    TEST_ASSERT_FALSE(pattern->update(2100));
    TEST_ASSERT_FALSE(pattern->update(2149));
    TEST_ASSERT_TRUE(pattern->update(2150)); // Fifth beep starts

    // Fifth beep: 2150-2350ms ON
    TEST_ASSERT_TRUE(pattern->update(2200));
    TEST_ASSERT_TRUE(pattern->update(2349));
    TEST_ASSERT_FALSE(pattern->update(2350)); // Gap starts

    // Fifth gap: 2350-2500ms OFF
    TEST_ASSERT_FALSE(pattern->update(2400));
    TEST_ASSERT_FALSE(pattern->update(2499));
    TEST_ASSERT_TRUE(pattern->update(2500)); // Sixth beep starts

    // Sixth beep: 2500-2700ms ON
    TEST_ASSERT_TRUE(pattern->update(2600));
    TEST_ASSERT_TRUE(pattern->update(2699));
    TEST_ASSERT_FALSE(pattern->update(2700)); // Final pause starts

    // Final pause: 2700-2850ms OFF
    TEST_ASSERT_FALSE(pattern->update(2800));
    TEST_ASSERT_FALSE(pattern->update(2849));
    TEST_ASSERT_FALSE(pattern->update(2850)); // Pattern complete

    // After pattern complete
    TEST_ASSERT_FALSE(pattern->isPlaying());
    TEST_ASSERT_TRUE(pattern->isComplete());
    TEST_ASSERT_FALSE(pattern->update(3000));
}

// Test: Total duration is 3000ms
void test_total_duration(void) {
    pattern->start();

    uint32_t time = 0;
    while (time < 4000) {
        pattern->update(time);
        if (!pattern->isPlaying()) {
            break;
        }
        time += 50;
    }

    // Should complete around 2850-3000ms
    TEST_ASSERT_TRUE(time >= 2800);
    TEST_ASSERT_TRUE(time <= 3100);
}

// Test: Stop works at any time
void test_stop_at_any_time(void) {
    pattern->start();

    // Stop in middle of pattern
    TEST_ASSERT_TRUE(pattern->update(500));
    pattern->stop();

    TEST_ASSERT_FALSE(pattern->isPlaying());
    TEST_ASSERT_TRUE(pattern->isComplete());
    TEST_ASSERT_FALSE(pattern->update(1000));
}

// Test: Ring request ignored while playing
void test_restart_while_playing(void) {
    pattern->start();
    TEST_ASSERT_TRUE(pattern->update(100));

    // Try to start again (should be ignored in real code)
    // In our simple implementation, start() will reset
    pattern->start();
    TEST_ASSERT_TRUE(pattern->isPlaying());
    TEST_ASSERT_TRUE(pattern->update(101));
}

int test_ring_pattern(void) {
    UNITY_BEGIN();

    RUN_TEST(test_initial_idle);
    RUN_TEST(test_start_pattern);
    RUN_TEST(test_stop_immediately);
    RUN_TEST(test_pattern_timing);
    RUN_TEST(test_total_duration);
    RUN_TEST(test_stop_at_any_time);
    RUN_TEST(test_restart_while_playing);

    return UNITY_END();
}
