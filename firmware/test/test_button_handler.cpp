#include "unity.h"
#include "../lib/ButtonHandler/ButtonHandler.h"

// Test fixture
static ButtonHandler* handler;

void setUp(void) {
    handler = new ButtonHandler(50, 1500);
}

void tearDown(void) {
    delete handler;
}

// Test: Initial state is no action
void test_initial_no_action(void) {
    TEST_ASSERT_FALSE(handler->isPressed());
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(0, false));
}

// Test: Short press detected
void test_short_press(void) {
    // Press
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(0, true));

    // Wait debounce
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(50, true));

    // Release before long press threshold
    TEST_ASSERT_EQUAL(ButtonHandler::SHORT_PRESS, handler->process(200, false));

    // No more actions
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(300, false));
}

// Test: Long press detected
void test_long_press(void) {
    // Press
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(0, true));

    // Wait through debounce
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(50, true));

    // Wait past long press threshold
    TEST_ASSERT_EQUAL(ButtonHandler::LONG_PRESS, handler->process(1600, true));

    // Release after long press
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(2000, false));
}

// Test: Bounce ignored
void test_bounce_ignored(void) {
    // Quick press-release within debounce
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(0, true));
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(20, false)); // Release before debounce

    // Should not register as short press
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(100, false));
}

// Test: Debounce period
void test_debounce_period(void) {
    // Press
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(0, true));

    // Still in debounce
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(30, true));

    // Release during debounce
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(40, false));

    // Should not register
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(100, false));
}

// Test: Pressed state tracking
void test_pressed_state(void) {
    TEST_ASSERT_FALSE(handler->isPressed());

    handler->process(0, true);
    handler->process(50, true); // After debounce

    TEST_ASSERT_TRUE(handler->isPressed());

    handler->process(200, false);
    TEST_ASSERT_FALSE(handler->isPressed());
}

// Test: Multiple short presses
void test_multiple_short_presses(void) {
    // First press
    handler->process(0, true);
    handler->process(50, true);
    TEST_ASSERT_EQUAL(ButtonHandler::SHORT_PRESS, handler->process(200, false));

    // Second press
    handler->process(300, true);
    handler->process(350, true);
    TEST_ASSERT_EQUAL(ButtonHandler::SHORT_PRESS, handler->process(500, false));

    // Third press
    handler->process(600, true);
    handler->process(650, true);
    TEST_ASSERT_EQUAL(ButtonHandler::SHORT_PRESS, handler->process(800, false));
}

// Test: Long press then release
void test_long_press_then_release(void) {
    handler->process(0, true);
    handler->process(50, true);

    // Long press detected
    TEST_ASSERT_EQUAL(ButtonHandler::LONG_PRESS, handler->process(1600, true));

    // Still pressed
    TEST_ASSERT_TRUE(handler->isPressed());

    // Release
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(2000, false));

    // No more actions
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(2100, false));
}

// Test: Reset clears state
void test_reset(void) {
    handler->process(0, true);
    handler->process(50, true);
    TEST_ASSERT_TRUE(handler->isPressed());

    handler->reset();
    TEST_ASSERT_FALSE(handler->isPressed());
    TEST_ASSERT_EQUAL(ButtonHandler::NONE, handler->process(100, true));
}

int test_button_handler(void) {
    UNITY_BEGIN();

    RUN_TEST(test_initial_no_action);
    RUN_TEST(test_short_press);
    RUN_TEST(test_long_press);
    RUN_TEST(test_bounce_ignored);
    RUN_TEST(test_debounce_period);
    RUN_TEST(test_pressed_state);
    RUN_TEST(test_multiple_short_presses);
    RUN_TEST(test_long_press_then_release);
    RUN_TEST(test_reset);

    return UNITY_END();
}
