#ifndef BUTTON_HANDLER_H
#define BUTTON_HANDLER_H

#include <stdint.h>

// Pure logic button handler - no Arduino calls, testable on host
class ButtonHandler {
public:
    ButtonHandler(uint16_t debounceMs = 50, uint16_t longPressMs = 1500);

    // Process button state. Returns action type.
    // Parameters:
    //   currentTime: current time in milliseconds
    //   buttonPressed: true if button is currently pressed (pin LOW for INPUT_PULLUP)
    enum Action {
        NONE,
        SHORT_PRESS,
        LONG_PRESS
    };

    Action process(uint32_t currentTime, bool buttonPressed);

    // Check if button is currently being held down
    bool isPressed() const;

    // Reset state
    void reset();

private:
    uint16_t debounceMs;
    uint16_t longPressMs;

    enum State {
        IDLE,
        DEBOUNCING,
        PRESSED,
        LONG_PRESS_DETECTED
    };

    State state;
    uint32_t stateStartTime;
    bool wasPressed;
    Action pendingAction;
};

#endif // BUTTON_HANDLER_H
