#-------------------------------------------------------------------------------
# Name:        Instrument
# Purpose:     Abstract super class for all instruments
#
# Author:      Laurent Carré
#
# Created:     29/11/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket


import threading
import logging
import time
from publisher import Publisher


_logger = logging.getLogger("ShipDataServer")


class InstrumentReadError(Exception):
    pass


class Instrument(threading.Thread):

    (NOT_READY, OPEN, CONNECTED, ACTIVE) = range(4)

    def __init__(self, name, timeout=30.0):
        super().__init__(name=name)
        self._name = name
        self._publishers = []
        self._configmode = False
        self._configpub = None
        self._startTS = 0
        self._total_msg = 0
        self._total_msg_s = 0
        self._last_msg_count = 0
        self._last_msg_count_s = 0
        self._timeout = timeout
        self._stopflag = False
        self._timer = None
        self._state = self.NOT_READY

    def start_timer(self):
        self._timer = threading.Timer(self._timeout, self.timer_lapse)
        self._timer.name = self._name + "timer"
        self._timer.start()

    def timer_lapse(self):
        _logger.debug("Timer lapse => total number of messages:%g" % self._total_msg)
        if self._total_msg-self._last_msg_count == 0:
            # no message received
            _logger.warning("Instrument %s:No NMEA messages received in the last %4.1f sec" %
                            (self._name, self._timeout))
        self._last_msg_count = self._total_msg
        self._last_msg_count_s = self._total_msg_s
        if not self._stopflag:
            self.start_timer()

    def run(self):
        self._startTS = time.time()
        self.start_timer()
        while not self._stopflag:
            if self._state == self.NOT_READY:
                if not self.open():
                    continue
            try:
                data = self.read()
                if type(data) == bytes:
                    if len(data) == 0:
                        _logger.warning("No data from %s => stop connection" % self._name)
                        self.close()
                        continue
                    else:
                        _logger.debug(data.decode().strip('\n\r'))
                else:
                    #  message is composite
                    _logger.debug(str(data))

            except (socket.timeout, InstrumentReadError):
                if self._stopflag:
                    break
                else:
                    continue
            # good data received - publish
            self._total_msg += 1
            self._state = self.ACTIVE
            self.publish(data)
        self.close()
        _logger.info("%s instrument thread stops"%self._name)

    def register(self, pub):
        self._publishers.append(pub)
        # print("Instrument %s register %s" % (self._name, pub.name()))

    def deregister(self, pub):
        try:
            self._publishers.remove(pub)
        except ValueError:
            _logger.warning("Removing non attached publisher %s" % pub.descr())
            pass

    def publish(self, msg):
        # print("Publishing on %d publishers" % len(self._publishers))
        for p in self._publishers:
            p.publish(msg)

    def send_cmd(self, msg):
        if not self._configmode:
            self._total_msg_s += 1
            self.send(msg)

    def total_input_msg(self):
        return self._total_msg

    def total_output_msg(self):
        return self._total_msg_s

    def name(self):
        return self._name

    def stop(self):
        _logger.info("Stopping %s instrument"% self._name)
        self._stopflag = True
        if self._timer is not None:
            self._timer.cancel()

    def open(self):
        raise NotImplementedError("To be implemented in subclass")

    def close(self):
        raise NotImplementedError("To be implemented in subclass")

    def read(self):
        raise NotImplementedError("To be implemented in subclass")

    def sender(self):
        return False

    def default_sender(self):
        return False
