#-------------------------------------------------------------------------------
# Name:        ikonvert
# Purpose:     DigitalYacht iKonvert interface
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import serial
import logging
import threading
import queue
import base64
import datetime

from instrument import Instrument, InstrumentReadError
from nmea2000_msg import NMEA2000Msg

_logger = logging.getLogger("ShipDataServer")
(UNKNOWN, STATUS, NOT_CONN, ACK, NAK, N2K) = range(6)


class iKonvertMsg():

    def __init__(self):
        self._type = UNKNOWN
        self._raw = None
        self._param = {}

    @staticmethod
    def from_bytes(data):
        msg = iKonvertMsg().decode(data)
        return msg

    def decode(self, data):
        self._raw = data

        if len(data) < 8:
            print("iKonvert incorrect data frame len=%d" % len(data))
            return None
        try:
            str_msg = data.decode().strip('\n\r')
        except UnicodeDecodeError:
            _logger.error("iKonvert message not valid %s" % str(data))
            return None

        _logger.debug("iKonvert received:%s" % str_msg)
        fields = str_msg.split(',')
        if len(fields) < 2:
            _logger.error("iKonvert improper message")
            return
        try:
            if fields[0][0] == '!':
                self._type = N2K
                self._param['pgn'] = fields[1]
                self._param['priority'] = fields[2]
                self._param['source'] = fields[3]
                self._param['destination'] = fields[4]
                self._param['timer'] = fields[5]
                self._param['payload'] = base64.b64decode(fields[6])
            elif fields[1][0] == '0':
                if len(fields[3]) == 0:
                    self._type = NOT_CONN
                else:
                    self._type = STATUS
                    self._param['bus_load'] = fields[2]
                    self._param['frame_errors'] = fields[3]
                    self._param['nb_devices'] = fields[4]
                    self._param['uptime'] = fields[5]
                    self._param['CAN_address'] = fields[6]
                    self._param['nb_rejected_PGN'] = fields[7]
            elif fields[1] == 'TEXT':
                self._type = NOT_CONN
                self._param['boot'] = fields[2]
            elif fields[1] == 'ACK':
                self._type = ACK
                self._param['message'] = fields[2]
            elif fields[1] == 'NAK':
                self._type = NAK
                self._param['error'] = fields[2]
            else:
                _logger.error("iKonvert Unknown message type %s %s" % (fields[0], fields[1]))
        except KeyError:
            _logger.error("iKonvert decoding error for message %s" % fields[0])
        return self

    def get(self, param):
        return self._param[param]

    @property
    def type(self):
        return self._type


class iKonvertRead(threading.Thread):

    def __init__(self, tty, instr_cbd, trace_file=None):
        self._tty = tty
        self._trace_file = trace_file
        super().__init__(name="IkonvertRead")

        self._stop_flag = False
        self._instr_cbd = instr_cbd

    def run(self) -> None:
        while self._stop_flag is False:
            try:
                data = self._tty.readline()
            except serial.SerialException as e:
                _logger.error("iKonvert read error: %s" % str(e))
                continue
            msg = iKonvertMsg.from_bytes(data)
            if msg is not None:
                self._instr_cbd[msg.type](msg)
                if self._trace_file is not None:
                    # only N2K messages are traced
                    if msg.type == N2K:
                        time_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f|")
                        self._trace_file.write(time_str)
                        self._trace_file.write(data.decode())
            else:
                _logger.error("iKonvert read error - suspected timeout")
        _logger.info("stopping iKonvert read")

    def stop(self):
        self._stop_flag = True


class iKonvert(Instrument):

    (IKIDLE, IKREADY, IKCONNECTED) = range(10, 13)
    (WAIT_MSG, WAIT_CONN, WAIT_ACKNAK) = range(20, 23)
    end_line = '\r\n'.encode()

    def __init__(self, opts):
        # opts["name"] = "iKonvert"
        super().__init__(opts)
        self._tty_name = opts["tty_name"]
        trace = opts.get("trace", None)
        self._mode = opts.get("mode", "ALL")  # ALL (send all PGN) or NORMAL (send only requested PGN)
        self._tty = None
        self._reader = None
        self._wait_sem = threading.Semaphore(0)
        self._lock = threading.Lock()  # to prevent re-entering some operations
        self._rx_pgn = []
        self._tx_pgn = []
        self._ikstate = self.IKIDLE
        self._wait_event = 0
        self._queue = queue.Queue(20)
        self._cmd_result = None
        if trace is not None:
            try:
                self._trace_fd = open(trace, "w")
            except IOError as e:
                _logger.error("iKonvert trace file %s %s" % (trace, str(e)))
                self._trace_fd = None
        else:
            self._trace_fd = None

    def open(self):
        # this section is critical
        self._lock.acquire()  # block
        _logger.info("iKonvert opening serial interface with initial state %d" % self._ikstate)
        if self._ikstate == self.IKCONNECTED:
            self._lock.release()
            return True
        if self._tty is None:
            try:
                self._tty = serial.Serial(self._tty_name, baudrate=230400, timeout=2.0)
            except serial.serialutil.SerialException as e:
                _logger.error("Opening serial interface for IKonvert: %s" % str(e))
                self._lock.release()
                return False
            _logger.info("iKonvert serial interface %s open" % self._tty_name)
        cb = {UNKNOWN: self.process_status, STATUS: self.process_status, NOT_CONN: self.process_status,
              ACK: self.process_acknak, NAK: self.process_acknak, N2K: self.process_n2k}
        if self._reader is None:
            self._reader = iKonvertRead(self._tty, cb,  self._trace_fd)
            self._reader.start()
        self.wait_status()
        if self._ikstate == self.IKREADY:
            # the gateway is not connected
            self.send_loc_cmd('N2NET_INIT', self._mode)
            self.wait_status()
        self._lock.release()
        if self._ikstate != self.IKCONNECTED:
            return False
        else:
            return True

    def process_n2k(self, msg):
        # print("N2K message received pgn %s" % msg.get('pgn'))
        n2k_msg = NMEA2000Msg( int(msg.get('pgn')),
                             int(msg.get('priority')),
                             int(msg.get('source')),
                             int(msg.get('destination')),
                             msg.get('payload'))
        # n2k_msg.display()
        try:
            self._queue.put(n2k_msg, block=False)
        except queue.Full:
            # just discard
            _logger.error("iKonvert read queue full")

    def process_status(self, msg):

        if msg.type == NOT_CONN:
            if self._ikstate == self.IKCONNECTED:
                _logger.info("iKonvert disconnected from NMEA network")
            self._ikstate = self.IKREADY
            if self._wait_event == self.WAIT_MSG:
                self._wait_event = 0
                self._wait_sem.release()
        else:
            if self._ikstate != self.IKCONNECTED:
                _logger.info("iKonvert connected to NMEA2000 network addr:%s" % msg.get('CAN_address'))
                self._ikstate = self.IKCONNECTED
            if self._wait_event == self.WAIT_CONN or self._wait_event == self.WAIT_MSG:
                self._wait_event = 0
                self._wait_sem.release()

    def process_acknak(self, msg):
        _logger.info("iKonvert ACK/NAK message")
        if self._wait_event == self.WAIT_ACKNAK:
            if msg.type == ACK:
                self._cmd_result = (ACK, msg.get('message'))
            else:
                self._cmd_result = (NAK, msg.get('error'))
            self._wait_event = 0
            self._wait_sem.release()

    def wait_status(self):
        self._wait_event = self.WAIT_MSG
        self._wait_sem.acquire()

    def send_loc_cmd(self, cmd, option=None, wait=ACK):
        self._cmd_result = None
        cmd_buf = "$PDGY,%s" % cmd
        if option is not None:
            cmd_buf = "%s,%s" % (cmd_buf, option)
        _logger.info("iKonvert sending command %s" % cmd_buf)
        self._tty.write(cmd_buf.encode())
        self._tty.write(self.end_line)
        self._tty.flush()
        if wait == ACK:
            self._wait_event = self.WAIT_ACKNAK
        else:
            self._wait_event = self.WAIT_MSG
        self._wait_sem.acquire()
        if wait == ACK:
            if self._cmd_result[0] == ACK:
                _logger.info("iKonvert CMD result OK")
            else:
                _logger.error("iKonvert CMD error %s" % self._cmd_result[1])

    def read(self):
        return self._queue.get()

    def stop(self):
        super().stop()
        if self._ikstate > self.IKIDLE:
            self.send_loc_cmd('N2NET_OFFLINE', wait=0)
            self.wait_status()
        self._reader.stop()
        self._queue.put(NMEA2000Msg(0))
        self._ikstate = self.IKIDLE

    def close(self):
        self._reader.join()
        self._tty.close()
        if self._trace_fd is not None:
            self._trace_fd.close()
        self._tty = None



