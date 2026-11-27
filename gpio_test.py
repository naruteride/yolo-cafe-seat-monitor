"""BCM 배선 점검. 라즈베리파이에서 python gpio_test.py 로 실행하세요."""

from contextlib import ExitStack
from time import sleep


def main():
    from gpiozero import Buzzer, LED

    with ExitStack() as devices:
        led_green = devices.enter_context(LED(17))
        led_yellow = devices.enter_context(LED(27))
        led_red = devices.enter_context(LED(22))
        buzzer = devices.enter_context(Buzzer(18))
        print("초록 LED 테스트")
        led_green.on()
        sleep(1)
        led_green.off()
        print("노랑 LED 테스트")
        led_yellow.on()
        sleep(1)
        led_yellow.off()
        print("빨강 LED + 부저 테스트")
        led_red.on()
        buzzer.on()
        sleep(0.5)
        buzzer.off()
        sleep(1)
        led_red.off()


if __name__ == "__main__":
    main()
