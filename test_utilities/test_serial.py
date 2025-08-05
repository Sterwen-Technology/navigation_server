import serial
import sys,os


def main():
    device = sys.argv[1]
    direction = sys.argv[2]
    tty = serial.Serial(device, 115200, timeout=20)
    if direction == "r":
        while True:
            try:
                print(tty.readline()[:-1].decode())
            except KeyboardInterrupt:
                break
    else:
        with open(sys.argv[3], "r") as fd:
            for line in fd:
                try:
                    tty.write(line.encode())
                except KeyboardInterrupt:
                    break
    tty.close()

if __name__ == '__main__':
    main()
