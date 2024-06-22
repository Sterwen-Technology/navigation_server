#-------------------------------------------------------------------------------
# Name:        mppt_reader
# Purpose:     server connected to Victron devices via VEDirect (serial 19200baud)
#   Both HEX protocol and Text protocol are handled
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import json
import serial
import threading
import logging
import time
from concurrent import futures
from collections import namedtuple
# sys.path.insert(0, "/data/solidsense/navigation/src")
import grpc
from generated.vedirect_pb2 import solar_output, request, MPPT_device
from generated.vedirect_pb2_grpc import solar_mpptServicer, add_solar_mpptServicer_to_server
from utilities.protobuf_utilities import set_protobuf_data


_logger = logging.getLogger("Energy_Server." + __name__)


class VEDirectException(Exception):
    pass


HexCommandContext = namedtuple('HexCommandContext', ['command', 'field', 'callback'])


class Vedirect(threading.Thread):

    (HEX, WAIT_HEADER, IN_KEY, IN_VALUE, IN_CHECKSUM) = range(5)

    def __init__(self, serialport, timeout, emulator=None):
        super().__init__(name="Vedirect")
        self.serialport = serialport
        try:
            self.ser = serial.Serial(serialport, 19200, timeout=timeout)
        except (serial.SerialException, BrokenPipeError) as e:
            _logger.error("Cannot open VEdirect serial interface %s" % str(e))
            raise VEDirectException

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
        self._hex_send_buffer = bytearray(32)
        self._hex_send_buffer[0] = ord(':')
        self._hex_cmd_context = None
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
        try:
            self._buffer[self._buflen] = byte
        except IndexError:
            _logger.error("Input buffer overflow %d" % self._buflen)
            self._buflen = 0
            return None

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
                message = self._buffer[:self._buflen]
                self.receive_hex_resp(message)
                self.state = self.WAIT_HEADER
                self._buflen = 0
                return None
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

    def send_hex_cmd(self, cmd: int, parameters=None):
        #
        # send a VEDirect HEX command
        #
        if 0 < cmd < 10:
            hex_cmd = 0x30 + cmd
        elif cmd < 17:
            hex_cmd = 0x31 + cmd
        else:
            raise VEDirectException("Illegal HEX command")
        # inster the cmd in buffer
        self._hex_send_buffer[1] = hex_cmd
        cmd_size = 2
        # compute initial checksum
        checksum = 0x55 - cmd

        if parameters is not None:
            for length, value in parameters.items():
                bytes_val = value.to_bytes(length, 'big')
                nb_nibble_count = 0
                start = 0
                while nb_nibble_count < length:
                    checksum -= (bytes_val[start] * 16) + bytes_val[start + 1]
                    start += 2
                encoded_val = bytes_val.hex().upper().encode()
                self._hex_send_buffer[cmd_size:] = encoded_val
                cmd_size += length * 2
        # add checksum in buffer
        hex_checksum = checksum.to_bytes(2, 'big').hex().upper().encode()
        self._hex_send_buffer[cmd_size:] = hex_checksum
        cmd_size += 2
        self._hex_send_buffer[cmd_size] = 0x10
        _logger.debug("VE.Direct send HEX message:%s" % self._hex_send_buffer[:cmd_size + 1])
        try:
            self.ser.write(memoryview(self._hex_send_buffer[:cmd_size + 1]))
        except (serial.SerialException, BrokenPipeError) as e:
            _logger.error(f"VE Direct: Error writing HEX command {e} on tty {self.serialport}")
            raise VEDirectException

    def receive_hex_resp(self, message: bytearray):
        _logger.debug("VE.direct receive HEX response:%s" % message.hex())
        response_id = message[0]











class MPPT_Servicer(solar_mpptServicer):

    solar_output_v = [('I', 'current', float, 0.001),
                      ('V', 'voltage', float, 0.001),
                      ('PPV', 'panel_power', float, 1.0)]

    device_status_v = [('PID', 'product_id', str, None),
                       ('FW', 'firmware', str, None),
                       ('SER#', 'serial', str, None),
                       ('ERR', 'error', int, 1),
                       ('CS', 'state', int, 1),
                       ('MPPT', 'mppt_state', int, 1),
                       ('H21', 'day_max_power', float, 1.0), # W
                       ('H20', 'day_power', float, 10.0)  # Wh
                       ]

    def __init__(self, reader):
        self._reader = reader

    def GetDeviceInfo(self, request, context):
        _logger.debug("GRPC request GetDevice")
        packet = self._reader.lock_get_data()
        ret_data = MPPT_device()
        if packet is not None:
            set_protobuf_data(ret_data, self.device_status_v, packet)
        self._reader.unlock_data()
        return ret_data

    def GetOutput(self, request, context):
        _logger.debug("GRPC request GetOutput")
        packet = self._reader.lock_get_data()
        ret_val = solar_output()
        if packet is not None:
            data_age = time.monotonic() - packet['timestamp']
            if data_age > 30.0:
                _logger.error("Vedirect outdated data by %5.1f seconds" % data_age)
            set_protobuf_data(ret_val, self.solar_output_v, packet)
        self._reader.unlock_data()
        return ret_val


class GrpcServer:

    def __init__(self, opts, reader):
        port = opts.port
        address = "0.0.0.0:%d" % port
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_solar_mpptServicer_to_server(MPPT_Servicer(reader), self._server)
        self._server.add_insecure_port(address)
        _logger.info("MPPT server ready on address:%s" % address)

    def start(self):
        self._server.start()
        _logger.info("MPPT server started")

    def wait(self):
        self._server.wait_for_termination()


class VEdirect_simulator:

    def __init__(self, filename, serial_emu=None):
        self._fd = open(filename, 'r')
        _logger.info("Opening simulator on file name:%s" % filename)
        self._ser = serial_emu
        self._lock = threading.Lock()
        #self._lock.acquire()

    def lock_get_data(self):

        try:
            line = self._fd.readline()
            _logger.debug(line)
        except IOError as e:
            _logger.error(str(e))
            # self._lock.release()
            return None
        if self._ser is not None:
            self._ser.send(line.encode())
        packet = json.loads(line)
        packet['timestamp'] = time.monotonic()
        return packet

    def start(self):
        pass

    def wait_lock(self):
        pass
        # self._lock.acquire()

    def unlock_data(self):
        pass
