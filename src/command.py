import socket
import sys
from argparse import ArgumentParser


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=int,
                   default=4502,
                   help="Listening port for console input, default is 4502")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='127.0.0.1',
                   help="IP address or URL for navigation server, default 127.0.0.1")
    p.add_argument('-c', '--command', action="store", type=str)
    return p


parser = _parser()


class Options(object):
    def __init__(self, p):
        self.parser = p
        self.options = None

    def __getattr__(self, name):
        if self.options is None:
            self.options = self.parser.parse_args()
        try:
            return getattr(self.options, name)
        except AttributeError:
            raise AttributeError(name)


def main():
    opts = Options(parser)
    print("Contacting navigation server %s:%d" % (opts.address, opts.port))
    try:
        s = socket.create_connection((opts.address, opts.port))
    except (OSError, socket.timeout) as e:
        print(e)
        return
    try:
        cmd = opts.command
    except AttributeError:
        return
    s.sendall(cmd.encode())
    while True:
        try:
            resp = s.recv(256)
        except OSError as e:
            print(e)
            break
        if len(resp) == 0:
            break
        resp = resp.decode()
        if resp == "END":
            break
        print(resp)


if __name__ == '__main__':
    main()
