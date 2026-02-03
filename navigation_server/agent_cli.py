#-------------------------------------------------------------------------------
# Name:        agent_cli.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     30/12/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
import logging
import time
from argparse import ArgumentParser

from navigation_server.router_common import GrpcClient, AgentClient, GrpcAccessException

_logger = logging.getLogger("ShipDataServer")


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=int,
                   default=4545,
                   help="Console listening port, default 4545")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='127.0.0.1',
                   help="IP address for Navigation server, default is localhost")
    p.add_argument("-c", "--certificate", action="store", type=str, default=None,
                   help="Certificate file to use, default is None")
    p.add_argument("-st", "--start", action="store", type=str, default=None,
                   help="Start a specific process")
    p.add_argument("-sp", "--stop", action="store", type=str, default=None,
                   help="Stop a specific process")

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


class ProcessManager(object):
    def __init__(self, agent):
        self._processes = None
        self._agent = agent
        self._system_proxy = agent.system_cmd('status')

    def refresh_processes(self):
        try:
            processes = self._system_proxy.get_processes()
        except GrpcAccessException:
            return
        self._processes = {p.name: p for p in processes}

    def display_processes(self):
        for proc in self._processes.values():
            print(f"{proc.name}\t\t{proc.state}")

    def display_status(self):
        print(f"Connected to:{self._system_proxy.hostname} - version:{self._system_proxy.version}")

    def process_cmd(self, cmd, process_name):
        if process_name not in self._processes:
            _logger.error(f"Unknown process {process_name}")
            return
        self._agent.process_cmd(cmd, process_name)
        time.sleep(1)
        self.refresh_processes()

    def start_process(self, process_name):
        self.process_cmd('start', process_name)
        


def main():
    options = Options(parser)
    # logger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)

    # Now we try to connect to the server
    secure_grpc = False
    if options.certificate is None:
        default= os.path.join(os.getenv('HOME'), 'certificates', 'nav_ca_cert.pem')
        if os.path.exists(default):
            _logger.info(f"Using default certificate file:{default}")
            options.certificate = default

    if options.certificate is not None:
        try:
            with open(options.certificate, 'rb') as f:
                certificate = f.read()
                GrpcClient.set_ca_certificate(certificate)
                secure_grpc = True
        except (FileNotFoundError, IOError) as e:
            _logger.error(e)


    navigation_agent_server = GrpcClient.get_client(f"{options.address}:{options.port}", secure=secure_grpc)
    agent = AgentClient()
    navigation_agent_server.add_service(agent)
    navigation_agent_server.connect()
    if not navigation_agent_server.wait_connect(10.):
        # if no response from the agent server, let's give up
        _logger.error("No agent available")
        return
    process_manager = ProcessManager(agent)
    process_manager.refresh_processes()
    process_manager.display_status()
    process_manager.display_processes()
    if options.start is not None:
        process_manager.start_process(options.start)
        process_manager.display_processes()



if __name__ == '__main__':
    main()


