#-------------------------------------------------------------------------------
# Name:        mppt_reader
# Purpose:     server connected to Victron MPPT
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import json
import serial
import threading
import logging
import sys
import socket
import time
from argparse import ArgumentParser
from concurrent import futures

import grpc
import vedirect_pb2
import vedirect_pb2_grpc


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-i', '--interface', action='store', type=str, default='/dev/ttyUSB4')
    p.add_argument('-p', '--port', action="store", type=int, default=4505)
    p.add_argument('-s', '--serial_port', action="store", default=4507)
    p.add_argument('-sim', '--simulator', action="store")

    return p


parser = _parser()
_logger = logging.getLogger("MPPT_Server")


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


class Vedirect(threading.Thread):

    (HEX, WAIT_HEADER, IN_KEY, IN_VALUE, IN_CHECKSUM) = range(5)

    def __init__(self, serialport, timeout, emulator):
        super().__init__(name="Vedirect")
        self.serialport = serialport
        try:
            self.ser = serial.Serial(serialport, 19200, timeout=timeout)
        except serial.SerialException as e:
            _logger.error("Cannot open VEdirect serial interface %s" % str(e))
            raise

        self._emulator = emulator
        self.header1 = ord('\r')
        self.header2 = ord('\n')
        self.hexmarker = ord(':')
        self.delimiter = ord('\t')
        self.key = ''
        self.value = ''
        self.bytes_sum = 0
        self.state = self.WAIT_HEADER
        self._results = ({}, {})
        self._active = 0
        self.dict = self._results[self._active]
        self._data_dict = None
        self._lock = threading.Lock()
        self._buffer = bytearray(512)
        self._buflen = 0
        # self._ts = 0

    def lock_data(self):
        # _logger.info("Locking data lock=%s" % self._lock.locked())
        if not self._lock.acquire(blocking=True, timeout=1.0):
            _logger.error("Vedirect data lock timeout")

    def unlock_data(self):
        try:
            self._lock.release()
        except RuntimeError:
            _logger.error("Vedirect data lock release error")
        # _logger.info("Unlocking data")

    def input(self, byte):
        self._buffer[self._buflen] = byte
        self._buflen += 1

        if byte == self.hexmarker and self.state != self.IN_CHECKSUM:
            self.state = self.HEX
        if self.state == self.WAIT_HEADER:
            self.bytes_sum += byte
            if byte == self.header1:
                self.state = self.WAIT_HEADER
            elif byte == self.header2:
                self.state = self.IN_KEY
            return None
        elif self.state == self.IN_KEY:
            self.bytes_sum += byte
            if byte == self.delimiter:
                if self.key == 'Checksum':
                    self.state = self.IN_CHECKSUM
                else:
                    self.state = self.IN_VALUE
            else:
                self.key += chr(byte)
            return None
        elif self.state == self.IN_VALUE:
            self.bytes_sum += byte
            if byte == self.header1:
                self.state = self.WAIT_HEADER
                self.dict[self.key] = self.value
                self.key = ''
                self.value = ''
            else:
                self.value += chr(byte)
            return None
        elif self.state == self.IN_CHECKSUM:
            self.bytes_sum += byte
            self.key = ''
            self.value = ''
            self.state = self.WAIT_HEADER
            if self.bytes_sum % 256 == 0:
                self.bytes_sum = 0
                return self.dict
            else:
                self.bytes_sum = 0
        elif self.state == self.HEX:
            self.bytes_sum = 0
            if byte == self.header2:
                self.state = self.WAIT_HEADER
        else:
            raise AssertionError()

    def run(self):
        while True:
            data = self.ser.read()
            for byte in data:
                packet = self.input(byte)
                if packet is not None:
                    # ok we have a good packet
                    self.lock_data()
                    self.dict['timestamp'] = time.monotonic()
                    # swap the dict.
                    self._data_dict = self.dict
                    self._active = not self._active
                    self.dict = self._results[self._active]
                    self.unlock_data()
                    if self._emulator is not None:
                        self._emulator.send(self._buffer[:self._buflen])
                    # _logger.debug(self._buffer[:self._buflen])
                    self._buflen = 0

    def lock_get_data(self):
        self.lock_data()
        return self._data_dict


class MPPT_Servicer(vedirect_pb2_grpc.solar_mpptServicer):

    solar_output_v = [('I', 'current', float, 0.001),
                      ('V', 'voltage', float, 0.001),
                      ('PPV', 'panel_power', float, 1.0)]

    def __init__(self, reader):
        self._reader = reader

    @staticmethod
    def set_data(result, keys, packet):
        for key, attr, type_v, scale in keys:
            if type_v is not None:
                val = type_v(packet[key]) * scale
            else:
                val = packet[key]
            object.__setattr__(result, attr, val)

    def GetDeviceInfo(self, request, context):
        pass

    def GetOutput(self, request, context):
        _logger.debug("GRPC request GetOutput")
        packet = self._reader.lock_get_data()
        ret_val = vedirect_pb2.solar_output()
        if packet is not None:
            data_age = time.monotonic() - packet['timestamp']
            if data_age > 30.0:
                _logger.error("Vedirect outdated data by %5.1f seconds" % data_age)
            self.set_data(ret_val, self.solar_output_v, packet)
        self._reader.unlock_data()
        return ret_val


class GrpcServer():

    def __init__(self, opts, reader):
        port = opts.port
        address = "0.0.0.0:%d" % port
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        vedirect_pb2_grpc.add_solar_mpptServicer_to_server(MPPT_Servicer(reader), self._server)
        self._server.add_insecure_port(address)
        _logger.info("MPPT server ready on address:%s" % address)

    def start(self):
        self._server.start()
        _logger.info("MPPT server started")


class UDPSerialEmulator:

    def __init__(self, port):

        self._socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self._address = ('0.0.0.0', port)
        # self._socket.bind(self._address)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send(self, msg):
        _logger.debug("Sending UDP packet to %s:%d" % self._address)
        self._socket.sendto(msg, self._address)


class TCPSerialEmulator(threading.Thread):

    def __init__(self, port):
        super().__init__()
        self._address = ('0.0.0.0', port)
        #self._server = socket.create_server(self._address, family=socket.AF_INET, reuse_port=True)
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(('0.0.0.0', port))
        # self._socket.settimeout(self._timeout)
        self._connection = None
        self._remote = None

    def run(self):
        while True:
            _logger.debug("Serial emulator waiting for connection")
            self._server.listen()
            self._connection, self._remote = self._server.accept()
            _logger.info("New serial emulation from %s:%d" % self._remote)
            while True:
                try:
                    data = self._connection.recv(256)
                except socket.error as e:
                    _logger.info("Error receiving on serial emulator" + str(e))
                    self._connection.close()
                    self._connection = None
                    break

    def send(self, msg):
        if self._connection is not None:
            try:
                _logger.debug("Sending TCP packet to %s:%d" % self._remote)
                self._connection.sendall(msg)
            except (IOError, socket.error) as e:
                _logger.error("Error sending on serial emulator" + str(e))



class VEdirect_simulator():

    def __init__(self, filename, serial_emu=None):
        self._fd = open(filename, 'r')
        _logger.info("Opening simulator on file name:%s" % filename)
        self._ser = serial_emu
        self._lock = threading.Lock()
        self._lock.acquire()

    def lock_get_data(self):

        try:
            line = self._fd.readline()
        except IOError as e:
            _logger.error(str(e))
            self._lock.release()
            return None
        if self._ser is not None:
            self._ser.send(line.encode())
        return json.loads(line)

    def start(self):
        pass

    def wait_lock(self):
        self._lock.acquire()


def main():
    opts = parser.parse_args()
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)

    if opts.serial_port is not None:
        ser_emu = TCPSerialEmulator(opts.serial_port)
    else:
        ser_emu = None
    if opts.simulator is not None:
        reader = VEdirect_simulator(opts.simulator, ser_emu)
    else:
        reader = Vedirect(opts.interface, 10.0, ser_emu)

    server = GrpcServer(opts, reader)
    if ser_emu is not None:
        ser_emu.start()
    reader.start()
    server.start()

    if opts.simulator is not None:
        reader.wait_lock()
    else:
        reader.join()


if __name__ == '__main__':
    main()





