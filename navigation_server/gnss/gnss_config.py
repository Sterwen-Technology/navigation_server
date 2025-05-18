#-------------------------------------------------------------------------------
# Name:        gnss_config
# Purpose:     Configuration of Ublox M10 chip via UBX protocol
#
# Author:      Laurent Carré
#
# Created:     14/05/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging
import serial
import threading
import queue
import time
import sys
from argparse import ArgumentParser

from pynmeagps import UBX_PROTOCOL
from pyubx2 import (UBXMessage, UBXReader, UBXMessageError, POLL_LAYER_RAM, SET_LAYER_RAM)

# from navigation_server.router_common import NavThread

_logger = logging.getLogger("ShipDataServer."+__name__)


def _parser():
    p = ArgumentParser(sys.argv[0])
    p.add_argument('-r', '--reset', action='store', choices=['hard', 'shutdown', 'soft'], default=None)
    p.add_argument('-b', '--baudrate', action='store', type=int, default=38400)
    p.add_argument('-d', '--device', action='store', type=str, default='/dev/ttyUSB0')
    p.add_argument('-v', '--version', action='store_true')
    p.add_argument('-e', '--epoch', action='store', type=float, default=None)
    p.add_argument('-f', '--file', action='store', type=str)
    p.add_argument('-m', '--messages', action='store', choices=['get', 'set', 'show', 'default'], default=None)
    p.add_argument('-n','--navigation', action='store', choices=['get', 'set'], default=None)
    p.add_argument('-fmt', '--formatter', action='append', nargs=2)
    p.add_argument('-st', '--start', action='store_true')
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


class GNSSUbxIo(threading.Thread):

    def __init__(self, ubx_reader:UBXReader, in_queue: queue.Queue, out_queue: queue.Queue):
        super().__init__(name="GNSSUbxIO", daemon=True)
        self._reader = ubx_reader
        self._in_queue: queue.Queue = in_queue
        self._out_queue: queue.Queue = out_queue
        self._stop_flag = False

    def run(self):
        while not self._stop_flag:
            try:
                msg = self._out_queue.get(block=False)
                # print(f"Sending UBX message raw={msg.serialize().hex(' ', 2)}")
                self._reader.datastream.write(msg.serialize())
            except queue.Empty:
                pass
            except serial.SerialException as err:
                _logger.error(f"UBX write error {err}")
                break
            try:
                (raw_data , parsed_data) = self._reader.read()
            except UBXMessageError as err:
                _logger.error(f"UBX Read message error {err}")
                continue
            if parsed_data is not None:
                # print(f"Received UBX message: {parsed_data}")
                self._in_queue.put(parsed_data)
        self._reader.datastream.close()

    def stop(self):
        self._stop_flag = True

class GNSSConfigurator:

    default_navigation_conf = [
        ("CFG_NAVSPG_DYNMODEL", 5),  # SEA
        ("CFG_NAVSPG_UTCSTANDARD", 5), # EU
        ("CFG_RATE_MEAS", 125), # 125ms measurement period
        ("CFG_RATE_NAV", 2) # 1 epoch every second calculation
    ]

    nmea_messages = ['DTM', 'GGA', 'GLL', 'GNS', 'GRS', 'GSA', 'GST', 'GSV', 'RLM', 'RMC', 'VLW', 'VTG', 'ZDA']

    reset_mode = {'hard': 0, 'shutdown': 4, 'soft': 1}

    default_messages_rate = {'GGA': 4, 'RMC': 1, 'GSA': 8, 'GSV': 16}

    def __init__(self, serial_port:str):
        try:
            serial_stream = serial.Serial(serial_port, baudrate=38400, timeout=0.1)
        except serial.serialutil.SerialException as err:
            _logger.error(f"GNSS Config error opening {serial_port}: {err}")
            raise
        self._messages_configuration = None
        self._messages_rate = self.default_messages_rate.copy()
        self._msg_list = list(f"CFG_MSGOUT_NMEA_ID_{fmt}_UART1" for fmt in self.nmea_messages)
        self._actual_navigation_conf = {}
        self._ubx_reader = UBXReader(serial_stream, protfilter=UBX_PROTOCOL)
        self._in_queue = queue.Queue(10)
        self._out_queue = queue.Queue(5)
        self._ubx_io = GNSSUbxIo(self._ubx_reader, self._in_queue, self._out_queue)
        self._ubx_io.start()


    def stop(self):
        self._ubx_io.stop()

    def send_ubx_msg(self, msg: UBXMessage):
        self._out_queue.put(msg)

    def get_ubx_message(self) -> UBXMessage:
        msg = self._in_queue.get()
        return msg

    def get_ubx_configuration(self, keywords: list[str]):
        msg = UBXMessage.config_poll(POLL_LAYER_RAM, 0, keywords)
        # print("Configuration message:",msg)
        self.send_ubx_msg(msg)
        time.sleep(0.1)
        while True:
            msg =self.get_ubx_message()
            print(msg.identity)
            if msg.identity == 'CFG-VALGET':
                return msg

    def poll_message(self, msg_class, msg_id):
        msg = UBXMessage(ubxClass=msg_class,ubxID=msg_id, msgmode=2)
        self.send_ubx_msg(msg)
        time.sleep(0.1)
        return self.get_ubx_message()

    def ubx_set_message(self, msg_class, msg_id, wait=True, **kwargs):
        msg = UBXMessage(ubxClass=msg_class,ubxID=msg_id,msgmode=1, **kwargs)
        self.send_ubx_msg(msg)
        if wait:
            time.sleep(0.2)
            msg = self.get_ubx_message()
            if msg.identity != 'ACK-ACK':
                _logger.error("Error on SET message")

    def get_navigation_conf(self):
        conf_keys = list(vp[0] for vp in self.default_navigation_conf)
        # print(conf_keys)
        msg = self.get_ubx_configuration(conf_keys)
        for keyword,val in self.default_navigation_conf:
            self._actual_navigation_conf[keyword] = getattr(msg, keyword)
        return self._actual_navigation_conf

    def set_ubx_configuration(self, key_values_pairs) -> bool:
        msg = UBXMessage.config_set(SET_LAYER_RAM, 0, key_values_pairs)
        self.send_ubx_msg(msg)
        time.sleep(0.2)
        msg = self.get_ubx_message()
        if msg.identity == 'ACK-ACK':
            print("UBX set configuration successful")
            return True
        else:
            return False

    def set_default_navigation_conf(self):
        self.set_ubx_configuration(self.default_navigation_conf)

    def get_messages_rate(self):
        self._messages_configuration = self.get_ubx_configuration(self._msg_list)
        return self._messages_configuration

    def update_messages_rate(self):
        for key in self._messages_rate.keys():
            idx = self.nmea_messages.index(key)
            self._messages_rate[key] = getattr(self._messages_configuration, self._msg_list[idx])

    def set_nmea_msg_rate(self, fmt:str, rate:int):
        if fmt not in self.nmea_messages:
            _logger.error(f"{fmt} is not an allowed formatter")
            return
        print("Setting rate for", fmt, "to:",rate,"epoch")
        self._messages_rate[fmt] = rate

    def list_messages_rate(self):
        idx = 0
        for msg in self.nmea_messages:
            rate = getattr(self._messages_configuration, self._msg_list[idx])
            print(f"{msg} rate is {rate}")
            idx += 1

    def set_messages_rate(self):
        idx = 0
        key_pair = []
        for fmt in self.nmea_messages:
            try:
                rate = self._messages_rate[fmt]
            except KeyError:
                rate = 0
            key_pair.append((self._msg_list[idx], rate))
            idx += 1
        print(key_pair)
        self.set_ubx_configuration(key_pair)

    def show_nmea_msg_rate(self):
        for fmt, rate in self._messages_rate.items():
            print(f"{fmt} output is every {rate} epoch")

    def reset_messages_conf(self):
        self._messages_rate = self.default_messages_rate.copy()

    def reset(self, mode:str):
        reset_mode = self.reset_mode[mode]
        self.ubx_set_message('CFG', 'CFG-RST', wait=False, navBbrMask=0, resetMode=reset_mode, reserved0=0)

    def get_version(self):
        msg = self.poll_message(0x0A, 0x04)
        zp = msg.swVersion.index(0)
        version = msg.swVersion[:zp].decode()
        return version

    def set_epoch(self, epoch:float):
        measurement_rate = int(epoch * 500)
        key_pair = [("CFG_RATE_MEAS", measurement_rate), ("CFG_RATE_NAV", 2)]
        self.set_ubx_configuration(key_pair)

def main():

    opts = Options(parser)
    try:
        configurator = GNSSConfigurator(opts.device)
    except Exception:
        return 2

    if opts.start:
        configurator.set_messages_rate()
        configurator.set_default_navigation_conf()
        configurator.stop()
        return 0

    if opts.version:
        print("Software version:",configurator.get_version())
    if opts.reset is not None:
        configurator.reset(opts.reset)
        time.sleep(2)
    if opts.formatter is not None:
        for fmt in opts.formatter:
            print(fmt)
            configurator.set_nmea_msg_rate(fmt[0].upper(), int(fmt[1]))
    if opts.messages is not None:
        if opts.messages == 'get':
            configurator.get_messages_rate()
            configurator.list_messages_rate()
        elif opts.messages == 'set':
            configurator.set_messages_rate()
        elif opts.messages == 'show':
            configurator.show_nmea_msg_rate()
        else:
            # default
            configurator.reset_messages_conf()
            configurator.set_messages_rate()

    if opts.navigation is not None:
        if opts.navigation == 'get':
            conf = configurator.get_navigation_conf()
            print(conf)
        else:
            configurator.set_default_navigation_conf()
    if opts.epoch is not None:
        if .1 < opts.epoch < 5.0 :
            configurator.set_epoch(opts.epoch)
        else:
            print("Epoch must be between 100ms and 5s")
    configurator.stop()
    return 0

if __name__ == '__main__':
    exit(main())



