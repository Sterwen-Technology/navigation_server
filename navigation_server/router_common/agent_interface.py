#-------------------------------------------------------------------------------
# Name:        agent_client
# Purpose:     agent client for processes registration
#
# Author:      Laurent Carré
#
# Created:     05/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import signal
from socket import gethostname
import time
import os


from navigation_server.router_common import (GrpcClient, ServiceClient, NavThread, MessageServerGlobals,
                                             GrpcAccessException, GrpcServer, ProtobufProxy, pb_enum_string)
from navigation_server.generated.agent_pb2_grpc import AgentStub
from navigation_server.generated.agent_pb2 import AgentCmdMsg, AgentResponse, NavigationSystemMsg
from navigation_server.generated.services_server_pb2 import ProcessState, Connection, Server, SystemProcessMsg

_logger = logging.getLogger("ShipDataServer." + __name__)

class SystemProcessMsgProxy(ProtobufProxy):

    def __init__(self, msg:SystemProcessMsg):
        super().__init__(msg)

    @property
    def state(self):
        return pb_enum_string(self._msg, 'state', self._msg.state)


class AgentResponseProxy(ProtobufProxy):

    def __init__(self, msg:AgentResponse):
        super().__init__(msg)

    @property
    def process_proxy(self) -> SystemProcessMsgProxy:
        return SystemProcessMsgProxy(self.process)

class NavigationSystemMsgProxy(ProtobufProxy):

    def __init__(self, msg:NavigationSystemMsg):
        super().__init__(msg)

    def get_processes(self):
        proc_list = []
        for proc in self._msg.processes:
            proc_list.append(SystemProcessMsgProxy(proc))
        return proc_list


def build_server_status_head(server) -> SystemProcessMsg:
    resp = SystemProcessMsg()
    resp.name = MessageServerGlobals.server_name
    resp.version = MessageServerGlobals.version
    resp.grpc_port = GrpcServer.grpc_port()
    resp.start_time = server.start_time_str()
    resp.state = ProcessState.RUNNING
    resp.pid = os.getpid()
    resp.console_present = server.console_present
    # some information are independent of the main server
    resp.hostname = gethostname()
    resp.purpose = MessageServerGlobals.configuration.server_purpose
    resp.settings = MessageServerGlobals.configuration.settings_file
    _logger.debug(f"Server status head: {resp}")
    return resp

class AgentClient(ServiceClient):

    def __init__(self):
        super().__init__(AgentStub)

    def register(self, process):
        response = self._server_call(self._stub.RegisterProcess, process, None)
        _logger.info(f"Registration result:{response.response}")

    def process_cmd(self, cmd: str, process_name: str):
        msg = AgentCmdMsg()
        msg.cmd = cmd
        msg.target = process_name
        try:
            response = self._server_call(self._stub.AgentCmd, msg, None)
        except GrpcAccessException:
            _logger.error(f"Grpc process_cmd error for {cmd} on {process_name}")
            return None

        if response.err_code != 0:
            _logger.error(f"Agent process command {cmd} on {process_name} returned an error: {response.response}")
            return None
        else:
            _logger.info(f"agent process_cmd {cmd} on {process_name}: {response.response}")
        return AgentResponseProxy(response)

    def system_cmd(self, cmd: str):
        msg = AgentCmdMsg()
        msg.cmd = cmd
        try:
            response = self._server_call(self._stub.AgentSystemCmd, msg, None)
        except GrpcAccessException:
            if cmd == 'status' and self.server_state() == GrpcClient.NOT_CONNECTED:
                self.server_connect()
            else:
                _logger.error(f"Grpc system_cmd error for {cmd}")
            return None
        if response.err_code != 0:
            _logger.error(f"Agent returning an error {response.err_code}: {response.response}")
            return None
        if cmd == 'status':
            return NavigationSystemMsgProxy(response.system)
        else:
            return response.err_code

    def get_port(self, process_name: str) -> int:
        resp = self.process_cmd('get_port', process_name)
        if resp is None:
            return 0
        else:
            return resp.grpc_port

    def get_log(self, process_name: str, line_callback):
        msg = AgentCmdMsg()
        msg.cmd = 'system_log'
        msg.target = process_name
        try:
            self._start_read_stream_to_callback(f"{process_name}-log_reader",self._stub.GetSystemLog, msg, line_callback)
        except GrpcAccessException:
            _logger.error(f"Error accessing server for logs on:{process_name}")
            return

    def stop_log(self):
        self._stop_read_stream()

class AgentInterfaceRunner(NavThread):

    def __init__(self, service, server):
        super().__init__(name="agent_interface", daemon=True)
        self._service = service
        self._server = server
        self._server_msg = None

    def send_confirmation(self):
        self._server_msg = build_server_status_head(MessageServerGlobals.main_server)
        self._server.connect()
        self.start()


    def nrun(self):
        counter = 0
        while True:
            try:
                _logger.debug("Sending registration to agent for %s" % self._server_msg.name)
                self._service.register(self._server_msg)
                _logger.info(f"{self._server_msg.name} registration complete")
            except GrpcAccessException:
                if counter > 20:
                    _logger.error(f"{self._server_msg.name} Unable to contact Agent for registration")
                    break
                time.sleep(30.0)
                self._server.connect()
                counter += 1
                continue
            break
        _logger.debug("Registration for %s completed" % self._server_msg.name)


class AgentInterface:

    def __init__(self):
        self._server = GrpcClient.get_client(MessageServerGlobals.agent_address)
        self._service = AgentClient()
        self._server.add_service(self._service)
        signal.signal(signal.SIGUSR1, self.sigusr1_handler)

    @property
    def service(self) -> AgentClient:
        return self._service

    def send_confirmation(self):
        runner = AgentInterfaceRunner(self._service, self._server)
        runner.send_confirmation()

    def sigusr1_handler(self, signum, frame):
        _logger.info("SIGUSR1 received")
        self.send_confirmation()


