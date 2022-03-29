

import socket

if __name__ == '__main__':

    server = socket.create_server(('0.0.0.0', 8282), reuse_port=True)
    server.listen()
    conn, address = server.accept()
    print("Connection from", address)
    while True:
        buf = bytearray()
        while True:
            data = conn.recv(1)
            buf.extend(data)
            if data == b'\r':
                break
        data_s = buf.decode()
        print(data_s)
        reply = "OK=>" + data_s + '\n'
        rep_data = reply.encode('utf-8')
        conn.sendall(rep_data)
