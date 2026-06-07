from time import sleep
from evdev import UInput, ecodes, KeyEvent


def click(uinput: UInput):
    uinput.write(ecodes.EV_KEY, ecodes.BTN_LEFT, KeyEvent.key_down)
    uinput.syn()
    sleep(0.025)
    uinput.write(ecodes.EV_KEY, ecodes.BTN_LEFT, KeyEvent.key_up)
    uinput.syn()


btn_key_codes: list[int] = []
for key_code, key_name in ecodes.keys.items():
    if isinstance(key_name, str):
        if key_name.startswith('BTN_'):
            btn_key_codes.append(key_code)
    else:
        for key_name_ in key_name:
            if key_name_.startswith('BTN_'):
                btn_key_codes.append(key_code)


def test_conflict_btns():
    """Test with `<input type="checkbox">`."""
    print("Waiting for 3 seconds before clicking...")
    sleep(3)
    events = {ecodes.EV_KEY: [ecodes.BTN_LEFT, -1]}
    for key_code in btn_key_codes:
        events[ecodes.EV_KEY][1] = key_code
        click(UInput(events=events))
        print(f"Test key {key_code}: {ecodes.keys[key_code]}")
        sleep(1)


if __name__ == "__main__":
    conflict_btns: list[tuple[int, str | tuple[str]]] = []
    non_conflict_btns: list[tuple[int, str | tuple[str]]] = []

    # Conflict key codes ∈ [288, 318] ∪ [544, 547] ∪ [704, 743],
    # in hexadecimal [0x120, 0x13e] ∪ [0x220, 0x223] ∪ [0x2c0, 0x2e7].
    # All are joystick bottons.
    # Source: [input-event-codes.h](https://github.com/torvalds/linux/blob/master/include/uapi/linux/input-event-codes.h)
    for key_code in btn_key_codes:
        if (288 <= key_code <= 318 or
            544 <= key_code <= 547 or
                704 <= key_code <= 743):
            conflict_btns.append((key_code, ecodes.keys[key_code]))
        else:
            non_conflict_btns.append((key_code, ecodes.keys[key_code]))

    print(f"Conflict buttons: {conflict_btns}")
    print(f"Non-conflict buttons: {non_conflict_btns}")
