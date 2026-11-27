"""Shared indicator bank using the BCM wiring from gpio_test.py."""

from contextlib import ExitStack


class Indicators:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self._devices = ExitStack()
        self._outputs = None
        self._alarm = False

    def __enter__(self):
        if self.enabled:
            from gpiozero import Buzzer, LED

            with ExitStack() as devices:
                green = devices.enter_context(LED(17))
                yellow = devices.enter_context(LED(27))
                red = devices.enter_context(LED(22))
                buzzer = devices.enter_context(Buzzer(18))
                self._outputs = green, yellow, red, buzzer
                self._devices = devices.pop_all()
        return self

    def update(self, states):
        if self._outputs is None:
            return
        states = set(states)
        alarm = "ABANDONED" in states
        in_use = bool(states.intersection({"OCCUPIED", "AWAY"}))
        green, yellow, red, buzzer = self._outputs
        green.value = states == {"EMPTY"}
        yellow.value = in_use and not alarm
        # GPIO Zero runs blink/beep in the background, independently of inference FPS.
        if alarm != self._alarm:
            if alarm:
                red.blink(on_time=0.5, off_time=0.5)
                buzzer.beep(on_time=0.2, off_time=0.2, n=2)
            else:
                red.off()
                buzzer.off()
            self._alarm = alarm

    def __exit__(self, *exc):
        try:
            self.update([])
        finally:
            self._outputs = None
            self._devices.close()
