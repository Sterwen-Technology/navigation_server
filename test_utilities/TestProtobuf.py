from generated.server_pb2 import nmea_msg
from nmea0183.nmea0183_msg import NMEA0183Msg


def main():

    top_msg = nmea_msg()
    frame = "$WIMWV,187.00,R,5.60,N,A*2E\r\n".encode()
    n183_msg = NMEA0183Msg(frame)
    n183_msg.as_protobuf(top_msg.N0183_msg)
    print(top_msg)


if __name__ == '__main__':
    main()