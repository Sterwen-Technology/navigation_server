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
    p.add_argument('-cp', '--config_port', action="store", type=int,
                   default=4501,
                   help="port for Shipmodul configuration server, default 4501")
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


class ShipModulInterface(threading.Thread):
    def __init__(self,address,port):
        super().__init__()
        self._address = address
        self._port = port
        self._publishers = []
        self._configmode = False
        self._configpub = None

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
        if pub == self._configpub:
            self._configmode = False
            self._configpub = None
            _logger.info("Switching to normal mode for Shipmodul")
        else:
            try:
                self._publishers.remove(pub)
            except KeyError:
                pass

    def publish(self, msg):
        if self._configmode:
            self._configpub.publish(msg)
        else:
            for p in self._publishers:
                p.publish(msg)

    def configModeOn(self, pub):
        if len(self._address) < 4:
            _logger.error("Missing target IP address for config mode")
            return False
        else:
            self._configmode = True
            self._configpub = pub
            _logger.info("Switching to configuration mode for Shipmodul")
            return True


class UDP_reader(ShipModulInterface):
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

    def send(self, msg):
        try:
            self._socket.sendto(msg,(self._address, self._port))
        except OSError as e:
            _logger.critical("Error writing on Shipmodul: %s" % str(e))
            raise


class TCP_reader(ShipModulInterface):

    def __init__(self,address,port):
        super().__init__(address, port)
        try:
            self._socket = socket.create_connection((address, port))
        except OSError as e:
            _logger.error("Connection error with shipmodul using TCP: %s" % str(e))
            raise

    def read(self):
        return self._socket.recv(256)

    def send(self, msg):
        try:
            self._socket.sendall(msg)
        except OSError as e:
            _logger.critical("Error writing on Shipmodul: %s" % str(e))
            raise


class NMEA_Publisher(threading.Thread):
    def __init__(self, sock, reader, server, address):
        super().__init__()
        self._socket = sock
        self._reader = reader
        self._server = server
        self._address = address
        self._queue = queue.Queue(20)
        # reader.register(self)

    def run(self):
        while True:
            msg = self._queue.get()
            try:
                self._socket.sendall(msg)
            except OSError as e:
                _logger.warning("Error writing data on %s:%d connection:%s => STOP" % (self._address[0], self._address[1], str(e)))
                break

        self._reader.deregister(self)
        self._socket.close()
        self._server.remove_pub(self._address)

    def publish(self, msg):
        try:
            self._queue.put(msg, block=False)
        except queue.Full:
            # need to empty the queue
            _logger.warning("Overflow on %s:%d connection" % (self._address[0], self._address[1]))
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

    def run(self):
        _logger.info("Data server ready")
        while True:
            _logger.info("Data server waiting for new connection")
            self._socket.listen(1)
            connection, address = self._socket.accept()
            _logger.info("New connection from IP %s port %d" % address)
            pub = NMEA_Publisher(connection, self._reader, self, address)
            self._reader.register(pub)
            self._pubs[address] = pub
            pub.start()

    def remove_pub(self, address):
        del self._pubs[address]


class ShipModulConfig(threading.Thread):

    def __init__(self, port, reader):
        super().__init__()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(('0.0.0.0', port))
        self._reader = reader
        self._pub = None

    def run(self):
        _logger.info("Configuration server ready")
        while True:
            _logger.info("Configuration server waiting for new connection")
            self._socket.listen(1)
            connection, address = self._socket.accept()
            _logger.info("New configuration connection from %s:%d" % address)
            pub = NMEA_Publisher(connection, self._reader, self, address)
            if not self._reader.configModeOn(pub):
                connection.close()
                continue
            self._pub = pub
            pub.start()
            _logger.info("Shipmodul configuration active")
            while pub.is_alive():
                try:
                    msg = connection.recv(256)
                    if len(msg) == 0:
                        break
                except OSError as e:
                    _logger.info("config socket read error: %s" % str(e))
                    break
                try:
                    self._reader.send(msg)
                except OSError:
                    break
            _logger.info("Connection with configuration application lost")
            self._reader.deregister(pub)
            connection.close()


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
    address = opts.address
    try:
        if opts.protocol == "UDP":
            _logger.info("opening UDP port %d" % port)
            reader = UDP_reader(address, port)
        else:

            _logger.info("opening port on host %s port %d" % (address, port))
            reader = TCP_reader (address, port)
            _logger.info("listening for NMEA sentences on host %s port %d" % (address, port))
    except OSError:
        return
    except Exception as e:
        _logger.critical(str(e))
        return

    server = NMEA_server(opts.server, reader)
    config_server = ShipModulConfig(opts.config_port, reader)
    server.start()
    config_server.start()
    reader.start()
    try:
        reader.join()
    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()
