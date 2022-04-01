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

    def __init__(self, serialport, timeout):
        super().__init__(name="Vedirect")
        self.serialport = serialport
        self.ser = serial.Serial(serialport, 19200, timeout=timeout)
        self.header1 = ord('\r')
        self.header2 = ord('\n')
        self.hexmarker = ord(':')
        self.delimiter = ord('\t')
        self.key = ''
        self.value = ''
        self.bytes_sum = 0
        self.state = self.WAIT_HEADER
        self.dict = {}

    (HEX, WAIT_HEADER, IN_KEY, IN_VALUE, IN_CHECKSUM) = range(5)

    def input(self, byte):
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

    def read_data_single(self):
        while True:
            data = self.ser.read()
            for single_byte in data:
                packet = self.input(single_byte)
                if packet is not None:
                    return packet

    def read_data_callback(self, callbackFunction):
        while True:
            data = self.ser.read()
            for byte in data:
                packet = self.input(byte)
                if packet is not None:
                    callbackFunction(packet)

    def run(self):
        while True:
            self.read_data_single()


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
        packet = self._reader.get_packet()
        ret_val = vedirect_pb2.solar_output()
        if packet is not None:
            self.set_data(ret_val, self.solar_output_v, packet)
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
        self._server = socket.create_server(self._address, family=socket.AF_INET, reuse_port=True)
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

    def get_packet(self):

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
    _logger.setLevel(logging.DEBUG)

    if opts.serial_port is not None:
        ser_emu = TCPSerialEmulator(opts.serial_port)
    else:
        ser_emu = None
    if opts.simulator is not None:
        reader = VEdirect_simulator(opts.simulator, ser_emu)
    else:
        reader = Vedirect(opts.interface, 10.0)

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





