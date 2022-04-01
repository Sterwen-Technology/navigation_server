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
                      ('PPV', 'panel_power', float, 0.001)]

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
        packet = self._reader.get_packet()
        ret_val = vedirect_pb2.solar_output()
        if packet is not None:
            self.set_data(ret_val, self.solar_output_v, packet)
        return ret_val


class GrpcServer():

    def __init__(self, opts, reader)
        port = opts.get('port', 4505)
        address = "0.0.0.0:%d" % port
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        vedirect_pb2_grpc.add_solar_mpptServicer_to_server(MPPT_Servicer(reader), self._server)
        self._server.add_insecure_port(address)

    def start(self):
        self._server.start()


class VEdirect_simulator():

    def __init__(self, filename):
        self._fd = open(filename, 'r')
        self._lock = threading.Lock()
        self._lock.acquire()

    def get_packet(self):

        try:
            line = self._fd.readline()
        except IOError as e:
            _logger.error(str(e))
            self._lock.release()
            return None
        return json.loads(line)

    def start(self):
        pass

    def wait_lock(self):
        self._lock.acquire()



def main():
    opts = parser.parse_args()

    if opts.simulator is not None:
        reader = VEdirect_simulator(opts.simulator)
    else:
        reader = Vedirect(opts.interface, 10.0)

    server = GrpcServer(opts, reader)
    reader.start()
    server.start()

    if opts.simulator is not None:
        reader.wait_lock()
    else:
        reader.join()


if __name__ == '__main__':
    main()





