from gpiozero import LED, Buzzer

led_green = LED(17)
led_yellow = LED(27)
led_red = LED(22)
buzzer = Buzzer(18)


def update_hardware_outputs(states):
    """states: 각 테이블 상태 문자열 리스트 (예: ['EMPTY', 'ABANDONED'])"""
    led_green.off()
    led_yellow.off()
    led_red.off()

    if STATE_ABANDONED in states:
        led_red.on()
        buzzer.on()
    else:
        buzzer.off()
        if STATE_OCCUPIED in states or STATE_AWAY in states:
            led_yellow.on()
        elif STATE_EMPTY in states:
            led_green.on()
