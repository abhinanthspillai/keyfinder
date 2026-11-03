#include "unity.h"
#include "../lib/ClapDetector/ClapDetector.h"

// Test fixture
static ClapDetector* detector;

void setUp(void) {
    detector = new ClapDetector(80, 150, 900, 400, 250, 2000);
}

void tearDown(void) {
    delete detector;
}

// Test: Single clap is ignored
void test_single_clap_ignored(void) {
    // Simulate a single clap
    TEST_ASSERT_FALSE(detector->processSound(0, true, false));  // Sound on
    TEST_ASSERT_FALSE(detector->processSound(50, false, false)); // Sound off
    TEST_ASSERT_FALSE(detector->processSound(1000, false, false)); // Gap > maxGap
    TEST_ASSERT_FALSE(detector->processSound(1100, false, false));
}

// Test: Double clap within valid gap is accepted
void test_double_clap_accepted(void) {
    // First clap
    TEST_ASSERT_FALSE(detector->processSound(0, true, false));
    TEST_ASSERT_FALSE(detector->processSound(50, false, false));

    // Second clap at 400ms (within 150-900ms range)
    TEST_ASSERT_TRUE(detector->processSound(400, true, false));
    TEST_ASSERT_FALSE(detector->processSound(450, false, false));
}

// Test: Gap too short is rejected
void test_gap_too_short_rejected(void) {
    // First clap
    TEST_ASSERT_FALSE(detector->processSound(0, true, false));
    TEST_ASSERT_FALSE(detector->processSound(50, false, false));

    // Second clap at 100ms (too short, min is 150ms)
    TEST_ASSERT_FALSE(detector->processSound(100, true, false));
    TEST_ASSERT_FALSE(detector->processSound(150, false, false));
}

// Test: Gap too long is rejected
void test_gap_too_long_rejected(void) {
    // First clap
    TEST_ASSERT_FALSE(detector->processSound(0, true, false));
    TEST_ASSERT_FALSE(detector->processSound(50, false, false));

    // Second clap at 1000ms (too long, max is 900ms)
    TEST_ASSERT_FALSE(detector->processSound(1000, true, false));
    TEST_ASSERT_FALSE(detector->processSound(1050, false, false));
}

// Test: Long noise pulse is ignored
void test_long_noise_ignored(void) {
    // Long pulse (500ms, exceeds maxPulse of 400ms)
    TEST_ASSERT_FALSE(detector->processSound(0, true, false));
    TEST_ASSERT_FALSE(detector->processSound(500, false, false));

    // Second clap after
    TEST_ASSERT_FALSE(detector->processSound(600, true, false));
    TEST_ASSERT_FALSE(detector->processSound(650, false, false));
}

// Test: Sound ignored during ring
void test_sound_ignored_during_ring(void) {
    // Start ringing state
    TEST_ASSERT_FALSE(detector->processSound(0, true, true));  // isRinging = true
    TEST_ASSERT_FALSE(detector->processSound(400, true, true));  // Still ignored
    TEST_ASSERT_FALSE(detector->processSound(800, false, true)); // Still ignored

    // After ring stops, still in cooldown
    TEST_ASSERT_FALSE(detector->processSound(2500, true, false)); // In cooldown
}

// Test: Sound ignored 2 seconds after ring
void test_sound_ignored_in_cooldown(void) {
    // Simulate ring ending
    detector->processSound(0, true, true);
    detector->processSound(3000, false, false); // Ring stopped

    // Still in cooldown for 2000ms
    TEST_ASSERT_FALSE(detector->processSound(3500, true, false));
    TEST_ASSERT_FALSE(detector->processSound(5000, true, false)); // 2s after, should reset

    // Now should work
    TEST_ASSERT_FALSE(detector->processSound(5100, true, false));
    TEST_ASSERT_FALSE(detector->processSound(5150, false, false));
    TEST_ASSERT_TRUE(detector->processSound(5300, true, false)); // Valid double clap
}

// Test: Three rapid sounds ignored
void test_three_rapid_sounds_ignored(void) {
    // First clap
    TEST_ASSERT_FALSE(detector->processSound(0, true, false));
    TEST_ASSERT_FALSE(detector->processSound(50, false, false));

    // Second clap
    TEST_ASSERT_TRUE(detector->processSound(400, true, false));
    TEST_ASSERT_FALSE(detector->processSound(450, false, false));

    // Third sound immediately after - should be ignored
    TEST_ASSERT_FALSE(detector->processSound(460, true, false));
    TEST_ASSERT_FALSE(detector->processSound(500, false, false));
}

int test_clap_detector(void) {
    UNITY_BEGIN();

    RUN_TEST(test_single_clap_ignored);
    RUN_TEST(test_double_clap_accepted);
    RUN_TEST(test_gap_too_short_rejected);
    RUN_TEST(test_gap_too_long_rejected);
    RUN_TEST(test_long_noise_ignored);
    RUN_TEST(test_sound_ignored_during_ring);
    RUN_TEST(test_sound_ignored_in_cooldown);
    RUN_TEST(test_three_rapid_sounds_ignored);

    return UNITY_END();
}
