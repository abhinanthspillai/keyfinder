#include "ButtonHandler.h"

ButtonHandler::ButtonHandler(uint16_t debounce, uint16_t longPress)
    : debounceMs(debounce),
      longPressMs(longPress),
      state(IDLE),
      stateStartTime(0),
      wasPressed(false),
      pendingAction(NONE) {
}

void ButtonHandler::reset() {
    state = IDLE;
    stateStartTime = 0;
    pendingAction = NONE;
}

bool ButtonHandler::isPressed() const {
    return state == PRESSED || state == LONG_PRESS_DETECTED;
}

ButtonHandler::Action ButtonHandler::process(uint32_t currentTime, bool buttonPressed) {
    Action action = pendingAction;
    pendingAction = NONE; // Consume pending action

    uint32_t elapsed = 0;
    if (stateStartTime > 0) {
        elapsed = currentTime - stateStartTime;
    }

    switch (state) {
        case IDLE:
            if (buttonPressed) {
                state = DEBOUNCING;
                stateStartTime = currentTime;
            }
            break;

        case DEBOUNCING:
            if (!buttonPressed) {
                // Released during debounce - ignore as bounce
                state = IDLE;
                stateStartTime = 0;
            } else if (elapsed >= debounceMs) {
                // Debounce passed, button is pressed
                state = PRESSED;
                stateStartTime = currentTime;
            }
            break;

        case PRESSED:
            if (!buttonPressed) {
                // Released - check if it was a short press
                state = IDLE;
                stateStartTime = 0;
                pendingAction = SHORT_PRESS;
            } else if (elapsed >= longPressMs) {
                // Held long enough for long press
                state = LONG_PRESS_DETECTED;
                pendingAction = LONG_PRESS;
            }
            break;

        case LONG_PRESS_DETECTED:
            if (!buttonPressed) {
                // Released after long press
                state = IDLE;
                stateStartTime = 0;
            }
            break;
    }

    wasPressed = buttonPressed;
    return action;
}
