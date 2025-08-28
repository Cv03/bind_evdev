import subprocess
from time import sleep
from evdev import KeyEvent, ecodes
from .bind_evdev import Bind


REMAP = {
    ecodes.KEY_RIGHTMETA: ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_INSERT: ecodes.KEY_SYSRQ,
}


bind = Bind(name='BT5.0 Keyboard', remap=REMAP)


def _reject_when_numlock_on(_: KeyEvent):
    return 'reject' if ecodes.LED_NUML in bind.device.leds() else 'accept'


numlock_off = bind.partial(prepend_before=[_reject_when_numlock_on])


@numlock_off(ecodes.KEY_KPSLASH, on='tap', with_modifiers=[ecodes.KEY_KPPLUS])
def brightness_up(_):
    bind.stroke.write_type(ecodes.KEY_BRIGHTNESSUP)


@numlock_off(ecodes.KEY_KPSLASH, on='tap_release')
def ctrl_z_undo(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_Z)


@numlock_off(ecodes.KEY_KPSLASH, on='hold')
def ctrl_x_cut(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_X)


@numlock_off(ecodes.KEY_KPASTERISK, on='tap_release')
def ctrl_y_redo(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_Y)


@numlock_off(ecodes.KEY_KPASTERISK, on='hold')
def ctrl_c_copy(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_C)


@numlock_off(ecodes.KEY_KPMINUS, on='tap_release')
def ctrl_a_select_all(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_A)


@numlock_off(ecodes.KEY_KPMINUS, on='hold')
def ctrl_v_paste(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_V)


@numlock_off(ecodes.KEY_KP7, with_modifiers=[ecodes.KEY_KPPLUS])
def volume_down(e: KeyEvent):
    bind.stroke.write_raw(ecodes.KEY_VOLUMEDOWN, e.keystate)


@numlock_off(ecodes.KEY_KP7)
def home(e: KeyEvent):
    bind.stroke.write_raw(ecodes.KEY_HOME, e.keystate)


@numlock_off(ecodes.KEY_KP8, on='tap', with_modifiers=[ecodes.KEY_KPPLUS])
def brightness_down(_):
    bind.stroke.write_type(ecodes.KEY_BRIGHTNESSDOWN)


@numlock_off(ecodes.KEY_KP9, with_modifiers=[ecodes.KEY_KPPLUS])
def volume_up(e: KeyEvent):
    bind.stroke.write_raw(ecodes.KEY_VOLUMEUP, e.keystate)


@numlock_off(ecodes.KEY_KP9)
def end(e: KeyEvent):
    bind.stroke.write_raw(ecodes.KEY_END, e.keystate)


def _set_kpenter_mode(to: str):
    def fn(_: KeyEvent):
        if ecodes.KEY_KPENTER not in bind.device.active_keys():
            return 'catch'
        mode: str | None = bind.data.get('kpenter_mode')
        if mode is None:
            bind.data['kpenter_mode'] = to
            if to == 'alt_tab':
                bind.stroke.write_raw(ecodes.KEY_LEFTALT, KeyEvent.key_down)
            return 'accept'
        elif mode == to:
            return 'accept'
        else:
            return 'catch'
    return fn


def _unset_kpenter_mode(_: KeyEvent):
    mode: str | None = bind.data.get('kpenter_mode')
    if mode == 'alt_tab':
        bind.stroke.write_raw(ecodes.KEY_LEFTALT, KeyEvent.key_up)
    bind.data['kpenter_mode'] = None


@numlock_off(ecodes.KEY_KP4,
             on='tap',
             with_modifiers=[ecodes.KEY_KPENTER],
             before=[_set_kpenter_mode('alt_tab')])
def alt_tab_shift_tab(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTSHIFT, ecodes.KEY_TAB)


@numlock_off(ecodes.KEY_KP5,
             on='tap',
             with_modifiers=[ecodes.KEY_KPENTER],
             before=[_set_kpenter_mode('alt_tab')])
def alt_tab_tab(_):
    bind.stroke.write_type(ecodes.KEY_TAB)


@numlock_off(ecodes.KEY_KP1,
             on='tap',
             with_modifiers=[ecodes.KEY_KPENTER],
             before=[_set_kpenter_mode('window_op')])
def meta_pagedown_minimize(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTMETA, ecodes.KEY_PAGEDOWN)


@numlock_off(ecodes.KEY_KP1)
def esc(e: KeyEvent):
    bind.stroke.write_raw(ecodes.KEY_ESC, e.keystate)


@numlock_off(ecodes.KEY_KP2,
             with_modifiers=[ecodes.KEY_KPENTER],
             on='tap',
             before=[_set_kpenter_mode('window_op')])
def meta_pageup_maximize(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTMETA, ecodes.KEY_PAGEUP)


@numlock_off(ecodes.KEY_KP2,
             on='tap')
def meta_minus_zoom_out(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTMETA, ecodes.KEY_MINUS)


@numlock_off(ecodes.KEY_KP3,
             with_modifiers=[ecodes.KEY_KPENTER],
             on='tap',
             before=[_set_kpenter_mode('window_op')])
def alt_f4_close_window(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTALT, ecodes.KEY_F4)


@numlock_off(ecodes.KEY_KP3,
             on='tap')
def meta_equal_zoom_in(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTMETA, ecodes.KEY_EQUAL)


numlock_off.no_op(ecodes.KEY_KPENTER, after=[_unset_kpenter_mode])


@numlock_off(ecodes.KEY_KP0, on='tap')
def command_goldendict_popup(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_C)
    sleep(0.03)
    run_result = subprocess.run(['wl-paste', '-n', '-t', 'text'],
                                capture_output=True, text=True)
    if run_result.returncode == 0 and run_result.stdout:
        _ = subprocess.run(['goldendict-ng', '-s', run_result.stdout])


@numlock_off(ecodes.KEY_KPDOT, on='tap')
def ctrl_backtick_copyq(_):
    bind.stroke.write_hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_GRAVE)


numpad_key_codes = (
    ecodes.KEY_KP0,
    ecodes.KEY_KP1,
    ecodes.KEY_KP2,
    ecodes.KEY_KP3,
    ecodes.KEY_KP4,
    ecodes.KEY_KP5,
    ecodes.KEY_KP6,
    ecodes.KEY_KP7,
    ecodes.KEY_KP8,
    ecodes.KEY_KP9,
    ecodes.KEY_KPDOT,
    ecodes.KEY_KPENTER,
    ecodes.KEY_KPPLUS,
    ecodes.KEY_KPMINUS,
    ecodes.KEY_KPASTERISK,
    ecodes.KEY_KPSLASH,
)
# Catch all unbound numpad key events.
for key_code in numpad_key_codes:
    numlock_off.no_op(key_code)

bind.serve()
