
import can



def main():

    try:
        bus = can.Bus(channel='can0', interface="socketcan", bitrate=250000)
    except can.CanError as e:
        print(e)
        return

    while True:
        try:
            msg = bus.recv(5.0)
        except can.CanError as e:
            print(e)
            break
        except KeyboardInterrupt:
            break
        if msg is not None:
            print(msg)

    bus.shutdown()


if __name__ == '__main__':
    main()