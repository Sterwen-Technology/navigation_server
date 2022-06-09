#-------------------------------------------------------------------------------
# Name:        data_server.py
# Purpose:     module for the TCP data server
#
# Author:      Laurent Carré
#
# Created:     29/02/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import socket
import time

from server_common import NavTCPServer
from publisher import *
from client_publisher import *
from nmea0183 import *


_logger = logging.getLogger("ShipDataServer"+".data_server")


class NMEAServer(NavTCPServer):

    '''
    Server class for NMEA clients

    '''
    publisher_class = {'transparent': NMEAPublisher, 'dyfmt': NMEA2000DYPublisher, 'stfmt': NMEA2000STPublisher}

    def __init__(self, options):
        super().__init__(options)
        self._instruments = []
        self._options = options
        self._nmea2000 = options.get_choice('nmea2000', ('transparent', 'dyfmt', 'stfmt'), 'transparent')
        self._connections = {}
        self._timer = None
        self._timer_name = self.name() + "-timer"
        self._sender = None
        self._sender_instrument = None

    def start_timer(self):
        self._timer = threading.Timer(self._heartbeat, self.heartbeat)
        self._timer.name = self._timer_name
        self._timer.start()

    def stop_timer(self):
        if self._timer is not None:
            self._timer.cancel()

    def run(self):
        _logger.info("%s ready listening on port %d" % (self.name(), self._port))
        self._sender_instrument = self.resolve_ref('sender')
        # print("Sender:", self._sender_instrument)
        self.start_timer()
        self._socket.settimeout(5.0)
        while not self._stop_flag:
            _logger.debug("%s waiting for new connection" % self.name())
            self._socket.listen(1)
            if len(self._connections) <= self._max_connections:
                try:
                    connection, address = self._socket.accept()
                except socket.timeout:
                    if self._stop_flag:
                        break
                    else:
                        continue
                if self._stop_flag:
                    connection.close()
                    break
            else:
                _logger.critical("Maximum number of connections (%d) reached:" % self._max_connections)
                time.sleep(5.0)
                continue

            _logger.info("New connection from IP %s port %d" % address)
            client = ClientConnection(connection, address, self)
            self._connections[address] = client
            # now create a publisher for all instruments
            pub = self.publisher_class[self._nmea2000](client, self._instruments)
            pub.start()
            if self._sender_instrument is not None and self._sender is None:
                self._sender = NMEASender(client, self._sender_instrument)
                self._sender.start()
            else:
                _logger.info("No instrument (sender) to send NMEA messages for server %s" % self.name())
            # end of while loop => the thread stops
        _logger.info("%s thread stops" % self.name())
        self._socket.close()

    def add_instrument(self, instrument):
        self._instruments.append(instrument)
        _logger.info("Server %s adding instrument %s" % (self.name(), instrument.name()))
        #if instrument.default_sender():
            # self._sender_instrument = instrument
        # now if we had some active connections we need to create the publishers
        for client in self._connections.values():
            pub = NMEAPublisher(client, instrument)
            pub.start()

    def remove_client(self, address):
        del self._connections[address]

    def remove_sender(self):
        self._sender = None

    def remove_instrument(self, instrument):
        _logger.info("Server %s removing instrument %s" % (self.name(), instrument.name()))
        try:
            self._instruments.remove(instrument)
        except ValueError:
            _logger.error("Server %s removing instrument %s failed" % (self.name(), instrument.name()))

    def heartbeat(self):
        _logger.info("%s heartbeat number of connections: %d"
                     % (self._name, len(self._connections)))
        if self._stop_flag:
            return
        self.start_timer()
        to_be_closed = []
        for client in self._connections.values():
            if client.msgcount() == 0:
                # no message during period
                _logger.info("Sending heartbeat on %s" % client.descr())
                heartbeat_msg = ZDA().message()
                if client.send(heartbeat_msg):
                    to_be_closed.append(client)
                client.reset_period()
        for client in to_be_closed:
            client.close()

    def stop(self):
        _logger.info("%s stopping" % self.name())
        self._stop_flag = True
        self.stop_timer()
        clients = self._connections.values()
        for client in clients:
            client._close()
        self._connections = {}

    def read_status(self):
        out = {}
        out['object'] = 'server'
        out['name'] = self.name()
        out['port'] = self._port
        if len(self._connections) > 0:
            connections = []
            for c in self._connections.values():
                connections.append(c.read_status())
            out['connections'] = connections
        else:
            out['connection'] = 'no connections'
        return out

