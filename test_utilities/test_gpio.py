
from nav_gpio import GpioLine

test_line = GpioLine('/dev/gpiochip0', 3)
test_out = GpioLine('/dev/gpiochip4', 14)

print(test_line.get())
test_out.set(0)