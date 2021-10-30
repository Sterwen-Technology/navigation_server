#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      Laurent
#
# Created:     14/04/2019
# Copyright:   (c) Laurent 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import sys,os

from argparse import ArgumentParser
import threading
import queue
import logging


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=int,
                   default=10110,
                   help="Listening port for Shipmodul input, default is 10110")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='',
                   help="IP address or URL for Shipmodul, no default")
    p.add_argument("-pr", "--protocol", action="store", type=str,
                   choices=['TCP','UDP'], default='TCP',
                   help="Protocol to read NMEA sentences, default TCP")
    p.add_argument("-s", "--server", action="store", type=int,
                   default=4500,
                   help="NMEA server port, default 4500")
    p.add_argument('-d', '--trace_level', action="store", type=str,
                   choices=["CRITICAL","ERROR", "WARNING", "INFO", "DEBUG"],
                   default="INFO",
                   help="Level of traces, default INFO")
    return p


parser = _parser()
_logger = logging.getLogger("ShipDataServer")


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


class ShipModul(threading.Thread):
    def __init__(self,address,port):
        super().__init__()
        self._address = address
        self._port = port
        self._publishers = []

    def close(self):
        self._socket.close()

    def run(self):
        while True:
            try:
                data = self.read()
                _logger.debug(data.decode().strip('\n\r'))
                if len(data) == 0:
                    _logger.warning("No data from shipmodul => stop connection")
                    break
            except KeyboardInterrupt:
                break
            self.publish(data)
        self.close()

    def register(self, pub):
        self._publishers.append(pub)

    def deregister(self, pub):
        self._publishers.remove(pub)

    def publish(self, msg):

        for p in self._publishers:
            p.publish(msg)


class UDP_reader(ShipModul):
    def __init__(self,address, port):
        super().__init__(address, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self._socket.bind(('',port))
        except OSError as e:
            _logger.error("Error connecting Shipmodul via UDP:%s" % str(e))
            raise

    def read(self):
        data, address = self._socket.recvfrom(256)
        # print("message from %s:%d" % address)
        return data


class TCP_reader(ShipModul):

    def __init__(self,address,port):
        super().__init__(address, port)
        try:
            self._socket = socket.create_connection((address, port))
        except OSError as e:
            _logger.error("Connection error with shipmodul using TCP: %s" % str(e))
            raise

    def read(self):
        return self._socket.recv(256)


class NMEA_Publisher(threading.Thread):
    def __init__(self, sock, reader, server, address):
        super().__init__()
        self._socket = sock
        self._reader = reader
        self._server = server
        self._address = address
        self._queue = queue.Queue(20)
        reader.register(self)
        self.start()

    def run(self):
        while True:
            msg = self._queue.get()
            try:
                self._socket.sendall(msg)
            except OSError as e:
                _logger.warning("Error writing data on %s %d connection:%s => STOP" % (self._address, str(e)))
                break

        self._reader.deregister(self)
        self._socket.close()
        self._server.remove_pub(self._address)

    def publish(self, msg):
        try:
            self._queue.put(msg, block=False)
        except queue.Full:
            # need to empty the queue
            _logger.warning("Overflow on %s connection" % self._address)
            try:
                discard = self._queue.get(block=False)
            except queue.Empty:
                pass
            self.publish(msg)


class NMEA_server(threading.Thread):
    def __init__(self, port, reader):
        super().__init__()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(('0.0.0.0', port))
        self._reader = reader
        self._pubs = {}
        self.start()

    def run(self):
        _logger.info("Data server ready")
        while True:
            self._socket.listen(1)
            connection, address = self._socket.accept()
            # print(address)
            _logger.info("New connection from IP %s port %d" % address)
            pub = NMEA_Publisher(connection, self._reader, self, address)
            self._pubs[address] = pub
            pub.run()

    def remove_pub(self, address):
        del self._pubs[address]


class ShipModulService(threading.Thread):

    def __init__(self, port, reader):
        super().__init__()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(('0.0.0.0', port))
        self._reader = reader
        self.start()


def main():
    opts = Options(parser)
    # looger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(opts.trace_level)
    # open the shipmodul port
    port = opts.port
    try:
        if opts.protocol == "UDP":
            _logger.info("opening UDP port %d" % port)
            reader = UDP_reader('', port)
        else:
            address = opts.address
            _logger.info("opening port on host %s port %d" % (address, port))
            reader = TCP_reader (address, port)
            _logger.info("listening for NMEA sentences on host %s port %d" % (address, port))
    except OSError:
        return
    except Exception as e:
        _logger.critical(str(e))
        return

    server = NMEA_server(opts.server, reader)
    reader.start()
    reader.run()
    server.run()
    reader.join()


if __name__ == '__main__':
    main()
