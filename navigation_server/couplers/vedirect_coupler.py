#-------------------------------------------------------------------------------
# Name:        vedirect_coupler
# Purpose:     coupler to Victron devices via VEDirect (serial 19200baud)
#   Both HEX protocol and Text protocol are handled
#
# Author:      Laurent Carré
#
# Created:     11/08/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging
import queue
import threading
from collections import namedtuple
import serial
import datetime
import time
import os

from navigation_server.router_common import MessageServerGlobals, NavGenericMsg, TRANSPARENT_MSG, NULL_MSG
from navigation_server.router_core import (Coupler, CouplerReadError, CouplerTimeOut, XDR, NMEA0183SentenceMsg,
                                           NMEA0183Sentences, NMEA0183Msg)
from navigation_server.log_replay import RawLogFile, LogReadError

_logger = logging.getLogger("ShipDataServer." + __name__)

HexCommandContext = namedtuple('HexCommandContext', ['command', 'field', 'callback'])


class VEDirectException(Exception):
    pass


class Vedirect(threading.Thread):

    (HEX, WAIT_HEADER, IN_KEY, IN_VALUE, IN_CHECKSUM) = range(5)

    def __init__(self, serialport, timeout, input_queue, trace_input=False):
        super().__init__(name="Vedirect", daemon=True)
        self._serialport = serialport
        self._timeout = timeout
        self._serial_fd = None
        self._queue = input_queue
        self.header1 = ord('\r')
        self.header2 = ord('\n')
        self.hexmarker = ord(':')
        self.delimiter = ord('\t')
        self.key = ''
        self.value = ''
        self.bytes_sum = 0
        self.state = self.WAIT_HEADER
        self.dict = {}
        self._stop_flag = False
        self._buffer = bytearray(512)
        self._buflen = 0
        self._hex_send_buffer = bytearray(32)
        self._hex_send_buffer[0] = ord(':')
        self._hex_cmd_context = None
        # self._ts = 0
        self._trace_fd = None
        if trace_input:
            trace_dir = MessageServerGlobals.configuration.get_option('trace_dir', '/var/log')
            date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
            filename = "TRACE-%s-%s.log" % ('VEDirect', date_stamp)
            filepath = os.path.join(trace_dir, filename)
            _logger.info("Opening trace file %s" % filepath)
            try:
                self._trace_fd = open(filepath, "w")
            except IOError as e:
                _logger.error("Trace file error %s" % e)

    def open(self):
        try:
            self._serial_fd = serial.Serial(self._serialport, 19200, timeout=self._timeout)
        except (serial.SerialException, BrokenPipeError) as e:
            _logger.error("Cannot open VEdirect serial interface %s" % str(e))
            return False
        return True

    def close(self):
        if self._serial_fd is not None:
            self._serial_fd.close()

    def stop(self):
        self._stop_flag = True

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
        msg_count = 0
        while True:
            if self._stop_flag:
                return
            try:
                data = self._serial_fd.read()
            except (serial.SerialException, serial.SerialTimeoutException):
                _logger.error(f"VEdirect read on port {self._serialport} that is not open")
                return

            for byte in data:
                packet = self.input(byte)
                if packet is not None:
                    # ok we have a good packet
                    if self._trace_fd is not None:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                        try:
                            trace = f"R{msg_count}#{timestamp}>{self._buffer[:self._buflen].hex()}\n"
                            self._trace_fd.write(trace)
                            self._trace_fd.flush()
                        except IOError as e:
                            _logger.error("Error writing VEdirect trace file %s" % e)
                            self._trace_fd.close()
                            self._trace_fd = None
                        except UnicodeDecodeError as e:
                            _logger.error("VEdirect Unicode error %s in buffer %s" % (e, self._buffer[:self._buflen]))

                    self.dict['timestamp'] = time.monotonic()
                    # send the dict in the queue
                    try:
                        self._queue.put(VEDirectMsg(self.dict), block=True, timeout=1.0)
                    except queue.Full:
                        _logger.error("VEDirect output queue full message lost")
                        continue
                    self.dict = {}
                    msg_count += 1
                    # _logger.debug(self._buffer[:self._buflen])
                    self._buflen = 0

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
            self._serial_fd.write(memoryview(self._hex_send_buffer[:cmd_size + 1]))
        except (serial.SerialException, BrokenPipeError) as e:
            _logger.error(f"VE Direct: Error writing HEX command {e} on tty {self._serialport}")
            raise VEDirectException

    def receive_hex_resp(self, message: bytearray):
        _logger.debug("VE.direct receive HEX response:%s" % message.hex())
        response_id = message[0]

    vedirect_fields = {'current': ('I', float, 0.001),
                        'voltage': ('V', float, 0.001),
                        'panel_power': ('PPV', float, 1.0),
                        'product_id':('PID', str, None),
                        'firmware': ('FW', str, None),
                        'serial': ('SER#', str, None),
                        'error': ('ERR', int, 1),
                        'state': ('CS', int, 1),
                        'mppt_state': ('MPPT', int, 1),
                        'day_max_power': ('H21', float, 1.0),  # W
                        'day_power':('H20', float, 10.0)  # Wh
                        }
    @staticmethod
    def value_from_message(msg, field_name):
        ved_field, field_type, coef = Vedirect.vedirect_fields[field_name]
        if field_type is float:
            value = float(msg[ved_field]) * coef
        elif field_type is int:
            value = int(msg[ved_field])
        else:
            value = msg[ved_field]
        return value


class VEDirectMsg(NavGenericMsg):

    def __init__(self, ve_dict: dict):
        super().__init__(TRANSPARENT_MSG, raw=ve_dict, msg=ve_dict)

    def printable(self) -> str:
        return str(self._msg)


class VEDirectLogReader(threading.Thread):

    def __init__(self, log_file, output_queue):
        self._log_file = log_file
        self._log_reader = None
        self._output_queue = output_queue
        super().__init__(name="VEDirectLogReader", daemon=True)
        self._stop_flag = False

    def open(self):
        try:
            self._log_reader = RawLogFile(self._log_file)
        except IOError:
            return False
        self._log_reader.load_file()
        if not self._log_reader.file_type.startswith('VEDirect'):
            _logger.error('VEDirectLogReader => wrong file type')
            return False
        self._log_reader.prepare_read()
        return True

    def stop(self):
        self._stop_flag = True

    def close(self):
        pass

    def run(self):
        while True:
            if self._stop_flag:
                break
            try:
                msg = self._log_reader.read_message()
            except LogReadError as err:
                if err.reason == "EOF":
                    _logger.info("Log Coupler End of file")
                else:
                    _logger.error("LogCoupler error in message index=%d msg:%s" %
                                  (self._log_file.index,
                                   err.reason))
                self._output_queue.put(NavGenericMsg(NULL_MSG))
                break
            # now let's decode
            # msg = msg.message.rstrip('\n')
            buffer = bytearray.fromhex(msg.message)
            msg_dec = {}
            fields = buffer.split(b'\r\n')
            for f in fields:
                if len(f) == 0:
                    continue
                label, value = f.split(b'\t')
                if label == b'Checksum':
                    break
                msg_dec[label.decode()] = value.decode()  # to be consistent all is converted in str
            try:
                self._output_queue.put(VEDirectMsg(msg_dec), timeout=10.0)
            except queue.Full:
                _logger.error("LogReader queue full, message discarded")


class VEDirectCoupler(Coupler):

    def __init__(self, opts):
        super().__init__(opts)
        self._input_queue = queue.Queue(5)
        self._interface = opts.get('interface', str, 'serial')
        if self._interface == 'serial':
            device = opts.get('device', str, '/dev/ttyUSB0')
            trace = opts.get('trace_vedirect', bool, False)
            self._reader = Vedirect(device, self._timeout, self._input_queue, trace)
        elif self._interface == 'simulation':
            log_file = opts.get('logfile', str, None)
            if log_file is None:
                raise ValueError
            self._reader = VEDirectLogReader(log_file, self._input_queue)
        else:
            raise ValueError
        if self._mode == self.NON_NMEA:
            self._convert_message = self.no_convert
        elif self._mode == self.NMEA0183:
            NMEA0183Sentences.set_talker(opts.get('talker', str, 'ST'))
            self._convert_message = self.convert_nmea0183
        else:
            raise ValueError

    def open(self):
        if self._reader.open():
            self._reader.start()
            return True
        else:
            return False

    def _read(self):
        msg = self._input_queue.get()
        if msg.type != NULL_MSG:
            msg = self._convert_message(msg)
        return msg

    def close(self):
        self._reader.close()

    def stop(self):
        if self._reader is not None:
            self._reader.stop()
        super().stop()

    def convert_nmea0183(self, msg):
        return mppt_nmea0183(msg.msg)

    def no_convert(self, msg):
        return msg


def mppt_nmea0183(dict_msg):
    sentence = XDR()
    sentence.add_transducer('I', "%.2f" % Vedirect.value_from_message(dict_msg, 'current'),
                            'A', 'MPPT Current')
    sentence.add_transducer('U', "%.2f" % Vedirect.value_from_message(dict_msg, 'voltage'),
                            'V', 'DC Circuit Voltage')
    sentence.add_transducer('W', "%.1f" % Vedirect.value_from_message(dict_msg, 'panel_power'),
                            'W', 'Solar Panel Power')
    return NMEA0183Msg(data=sentence.message())