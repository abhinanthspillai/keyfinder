#include "unity.h"

// External test runners
extern int test_clap_detector(void);
extern int test_ring_pattern(void);
extern int test_button_handler(void);

int main(void) {
    UNITY_BEGIN();

    // Run all test suites
    test_clap_detector();
    test_ring_pattern();
    test_button_handler();

    return UNITY_END();
}
