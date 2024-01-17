#-------------------------------------------------------------------------------
# Name:        nmea2000_msg
# Purpose:     Manages all NMEA2000/J1939 messages
#
# Author:      Laurent Carré
#
# Created:     26/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import sys
import os
from argparse import ArgumentParser
import logging
import json
import google.protobuf
import grpc


from nmea2000.nmea2k_pgndefs import PGNDefinitions
from utilities.global_variables import MessageServerGlobals
from nmea2000.nmea2k_manufacturers import Manufacturers
from generated.nmea2000_classes_gen import nmea2k_generated_classes
from generated.input_server_pb2_grpc import NMEAInputServerStub
from generated.nmea_messages_pb2 import server_cmd

_logger = logging.getLogger("ShipDataServer")


def _parser():

    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-x', '--xml', action="store", type=str,
                   default="PGNDefns.N2kDfn.xml")
    p.add_argument('-o', '--csv_out', action="store", type=str)
    p.add_argument('-i', '--input', action='store', type=str)
    p.add_argument('-d', '--trace_level', action="store", type=str,
                   choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                   default="INFO",
                   help="Level of traces, default INFO")
    p.add_argument('-p', '--print', action='store', type=str,
                   default='None')
    p.add_argument("-l", "--log", action="store", type=str,
                   help="Logfile for all incoming NMEA sentences")
    p.add_argument("-t", "--trace", action="store", type=str)
    p.add_argument('-f', '--filter', action='store', type=str)
    p.add_argument('-s', '--server', action='store', type=str)
    p.add_argument('-c', '--count', action='store', type=int, default=0)
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


class GrpcSender:

    def __init__(self, address):
        self._address = address
        self._channel = grpc.insecure_channel(self._address)
        self._stub = NMEAInputServerStub(self._channel)

    def send(self, pgn_obj):

        msg = pgn_obj.protobuf_message()
        # print(msg)
        try:
            resp = self._stub.pushDecodedNMEA2K(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("GRPC Server %s not accessible" % self._address)

    def check_status(self) -> bool:
        msg = server_cmd()
        msg.cmd = "TEST_STATUS"
        try:
            resp = self._stub.status(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("GRPC Server %s not accessible" % self._address)
            return False
        if resp.status == "SERVER_OK":
            return True
        else:
            return False


def main():
    opts = Options(parser)
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(opts.trace_level)

    MessageServerGlobals.manufacturers = Manufacturers('../def/Manufacturers.N2kDfn.xml')
    MessageServerGlobals.pgn_definitions = PGNDefinitions('../def/PGNDefns.N2kDfn.xml')

    # create stub
    sender = GrpcSender(opts.server)

    try:
        fp = open(opts.input, 'r')
    except IOError as err:
        _logger.error("Input file error: %s" % err)
        return
    try:
        pgn_list = json.load(fp)
    except json.JSONDecodeError as err:
        _logger.error("decode error:%s" % err)
        return
    for pgn_dict in pgn_list:
        pgn = pgn_dict['pgn']
        pgn_data = pgn_dict['data']
        pgn_class = nmea2k_generated_classes[pgn]
        protobuf_class = pgn_class.protobuf_class()
        pb_obj = protobuf_class()
        google.protobuf.json_format.ParseDict(pgn_data, pb_obj)
        pgn_obj = pgn_class()
        pgn_obj.from_protobuf(pb_obj)
        # print(pgn_obj)
        if sender.check_status():
            _logger.debug("Sending object to CAN CA=%s" % pb_obj)
            sender.send(pgn_obj)


if __name__ == '__main__':
    main()
