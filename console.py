#-------------------------------------------------------------------------------
# Name:        Console
# Purpose:     Console interface for navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------
import threading
import socket
import logging
import json

from server_common import *

_logger = logging.getLogger("ShipDataServer")


class Console(NavTCPServer):

    def __init__(self, port):
        super().__init__("Console", port)
        self._servers = {}
        self._instruments = {}
        self._injectors = {}
        self._connection = None

    def add_server(self, server):
        self._servers[server.name()] = server

    def add_instrument(self, instrument):
        self._instruments[instrument.name()] = instrument

    def run(self) -> None:
        _logger.info("Console starting")
        while not self._stop_flag:
            self._socket.listen(1)
            _logger.info("Console waiting for connection")
            try:
                self._connection, address = self._socket.accept()
            except socket.timeout:
                if self._stop_flag:
                    if self._connection is not None:
                        self._connection.close()
                    break
                else:
                    continue
            except OSError as e:
                if self._stop_flag:
                    break
                else:
                    raise
            _logger.info("New console connection from %s:%d" % address)

            while True:
                try:
                    cmd = self._connection.recv(1024)
                except OSError as e:
                    _logger.info("Error reading console socket: %s" % str(e))
                    break
                if len(cmd) == 0:
                    break
                self.process_cmd(cmd.decode())

            _logger.info("Console connection closed")
            self._connection.close()

        _logger.info("Console server stopping")
        self._socket.close()

    def stop(self):
        self._stop_flag = True
        if self._connection is not None:
            self._connection.close()
        self._socket.close()

    def process_cmd(self, cmd):
        #
        #  only trivial command for the moment
        _logger.info("Command received:%s" % cmd)
        if cmd == "STOP":
            server = self._servers['main']
            self.reply("Stopping all servers - navigation system will stop")
            self.reply("END")
            self.stop()
            server.stop_server()
        elif cmd == "INSTRUMENTS":
            self.instrument_status(cmd)
        elif cmd == "SERVERS":
            self.server_status(cmd)
        else:
            self.reply("Unknown command:%s" % cmd)

    def reply(self, msg):
        self._connection.sendall(msg.encode())

    def reply_end(self):
        self._connection.sendall("END".encode())
        self._connection.close()

    def instrument_status(self, cmd):
        self.reply("INSTRUMENTS")
        for name, inst in self._instruments.items():
            resp = "%s | msg in %d msg out %d\n" % (name, inst.total_input_msg(), inst.total_output_msg())
            print(resp)
            self.reply(resp)
        self.reply_end()

    def server_status(self, cmd):
        self.reply("SERVERS")
        server = self._servers['NMEAServer']
        out = server.read_status()
        resp = json.dumps(out)
        self.reply(resp)
        self.reply_end()
