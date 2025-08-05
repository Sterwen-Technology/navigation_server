import pylibi2c


def i2c_read_nmea(device):

    return_buffer = bytearray(128)
    start_index = 0
    read_length = 64
    while True:
        read_buffer = device.read(0xFF, read_length)
        # print(read_buffer)
        idx = 0
        for b in read_buffer:
            if b== 0xFF:
                idx += 1
            else:
                break
        # print("idx=", idx)
        if idx < read_length:
            end_frame = read_buffer.find(0xFF, idx)
            if end_frame < 0:
                end_frame = read_length
            # print("buffer=",read_buffer[:end_frame])
            while idx < end_frame:
                end_sentence = read_buffer.find(b'\n', idx, end_frame)
                # print("idx=",idx,"end_frame=",end_frame,"end sentence=",end_sentence, "start index", start_index,'c=',read_buffer[end_sentence])
                if end_sentence >= 0:
                    return_buffer[start_index:] = read_buffer[idx:end_sentence+1]
                    end_index = start_index + (end_sentence - idx) + 1
                    sentence = return_buffer[:end_index]
                    # print("yield:", sentence)
                    yield sentence
                    idx = end_sentence + 1
                    start_index = 0
                else:
                    return_buffer[start_index:] = read_buffer[idx: end_frame]
                    start_index += end_frame - idx
                    # print("break")
                    break
            # print("End of inner loop")


def main():

    device = pylibi2c.I2CDevice('/dev/i2c-6', 0x42)
    while True:
        try:
             for frame in i2c_read_nmea(device):
                print(frame.decode().rstrip('\r\n'))
        except KeyboardInterrupt:
            break


if __name__ == '__main__':
    main()
