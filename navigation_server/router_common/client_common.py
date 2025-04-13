#-------------------------------------------------------------------------------
# Name:        client_common
# Purpose:     super class with all client common functions
#
# Author:      Laurent Carré
#
# Created:     05/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import grpc
import logging

from navigation_server.router_common import GrpcAccessException


_logger = logging.getLogger("ShipDataServer." + __name__)


class GrpcClient:
    """
    The GrpcClient class facilitates interaction with a gRPC server.

    This class provides methods for establishing connections to a gRPC server,
    managing service stubs, and making server calls for both single and multiple
    responses. It also handles server communication errors and maintains the
    current connection state.

    Attributes:
        NOT_CONNECTED: Represents the initial or disconnected state of the client.
        CONNECTING: Represents the state when a connection attempt is in progress.
        CONNECTED: Represents the state when the client is successfully connected.
    """
    (NOT_CONNECTED, CONNECTING, CONNECTED) = range(10, 13)

    def __init__(self, server: str, use_request_id:bool = True):
        """
        Represents a client connection handler for a server.

        Parameters:
            server: this is a string in the form Address(or URL):port

        This class is responsible for managing the connection and communication
        with a server. It initializes essential attributes required to maintain
        the state of the connection, the server reference, and tracks any
        registered services or channels involved in the communication.

        Attributes:
            _server: The reference to the server with which the connection is
                established.
            _channel: Represents the communication channel for this client.
                Initially set to None.
            _services: A list that keeps track of the registered services
                associated with this client.
            _state: Indicates the current connection state of the client. This
                starts as NOT_CONNECTED.
            _req_id: A numerical identifier for tracking requests made by the
                client.
        """
        self._server = server
        self._channel = None
        self._services = []
        self._state = self.NOT_CONNECTED
        self._req_id = 0
        self._use_req_id = use_request_id

    def connect(self):
        """
        Connects to the gRPC server and initializes the stubs for the provided services.

        This method creates an insecure channel to the specified server and iterates
        through each service to initialize its gRPC stub. After successfully setting
        up the stubs, the connection state is updated to CONNECTING, and a log entry
        is created to indicate the connection status.

        """
        self._channel = grpc.insecure_channel(self._server)
        self._channel.subscribe(self.channel_callback)
        for service in self._services:
            service.create_stub(self._channel)
        self._state = self.CONNECTING
        _logger.info("Server stub created on %s => connecting" % self._server)

    def add_service(self, service):
        """
        Adds a service to the current server instance and initializes it based on the server's state.

        Parameters
        ----------
        service : Service
            The service instance to be added to the server.

        Raises
        ------
        None

        """
        self._services.append(service)
        service.attach_server(self)
        if self._state in (self.CONNECTING, self.CONNECTED):
            service.create_stub(self._channel)

    @property
    def state(self):
        return self._state

    @property
    def address(self):
        return self._server

    def server_call(self, rpc_func, req, response_class):
        """
        Performs a server call through gRPC client.

        This method invokes a remote procedure call on a gRPC server. The request
        ID is incremented for each call and assigned to the request object. The
        response is either processed by a response class, if provided, or returned
        as-is. Handles gRPC errors and updates the client state accordingly when
        connection is unavailable.

        Args:
            rpc_func: Callable
                The gRPC function representing the remote procedure call to be
                executed.
            req: Any
                The request object to be sent to the server. It must have an `id`
                attribute that gets updated to the current request identifier.
            response_class: Optional[Callable]
                A class or callable used to process and return the raw response,
                if provided. If not supplied, the raw response from the gRPC
                server is returned.

        Returns:
            Any: Processed response from the server or the raw response, depending
            on whether `response_class` is provided.

        Raises:
            GrpcAccessException:
                Raised if there is an error accessing the server or if a non-
                recoverable gRPC error occurs.
        """
        _logger.debug("gRPC Client server call")
        self._req_id += 1
        if self._use_req_id:
            req.id = self._req_id
        try:
            response = rpc_func(req)
            if response_class is not None:
                return response_class(response)
            else:
                return response
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"Error accessing server:{err.details()}")
                self._state = self.NOT_CONNECTED
            raise GrpcAccessException

    def server_call_multiple(self, rpc_func, req, response_class):
        """
        Provides functionality for making server calls to a gRPC service that respond with
        multiple responses. This function handles request IDs, logs server interactions,
        and manages errors including disconnections.

        Args:
            rpc_func: Callable
                The gRPC function being invoked for making the server call.
            req: Any
                The request object to send during the gRPC call.
            response_class: Optional[Callable]
                A class or callable to transform the responses from the server. If None,
                no transformation is applied.

        Yields:
            Any
                The responses from the server, either raw or transformed by the
                response_class provided.

        Raises:
            GrpcAccessException:
                If an error occurs during the gRPC call, especially when the server is
                unreachable or another server-specific error arises.
        """
        _logger.debug("gRPC Client server call with multiple responses")
        self._req_id += 1
        if self._use_req_id:
            req.id = self._req_id
        try:
            for response in rpc_func(req):
                if response_class is not None:
                    yield response_class(response)
                else:
                    yield response
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"Error accessing server:{err.details()}")
                self._state = self.NOT_CONNECTED
            raise GrpcAccessException

    def channel_callback(self, connectivity: grpc.ChannelConnectivity):
        if connectivity == grpc.ChannelConnectivity.READY:
            _logger.info("GRPC Channel Ready")
            self._ready = True
        elif connectivity == grpc.ChannelConnectivity.IDLE:
            _logger.info("GRPC Channel IDLE")
            # self._ready = False
        elif connectivity == grpc.ChannelConnectivity.CONNECTING:
            _logger.info("GRPC Channel Connecting")
        elif connectivity == grpc.ChannelConnectivity.SHUTDOWN:
            _logger.info("GRPC Channel Shutdown")


class ServiceClient:
    """
    ServiceClient abstracts and manages gRPC client-server communications.

    This class provides an interface to interact with gRPC services, allowing
    the attachment of a gRPC server object, creation of stubs, and handling
    RPC calls either for single or multiple responses. The ServiceClient class
    is designed as a utility to encapsulate common gRPC client interactions,
    offering streamlined functionality for communicating with servers.

    Attributes:
        _stub_class: The gRPC stub class associated with the service.
        _stub: Represents the gRPC stub instance created using the stub class.
               It is None by default until initialized.
        _server (GrpcClient): The server object to which the client is attached.
               Used for executing various RPC calls.
    """
    def __init__(self, stub_class):
        self._stub_class = stub_class
        self._stub = None
        self._server: GrpcClient = None

    def attach_server(self, server:GrpcClient):
        """
        Attaches a gRPC client server to the current instance to establish a server
        connection.

        Args:
            server (GrpcClient): The gRPC client instance to be attached.
        """
        self._server = server

    def create_stub(self, channel):
        self._stub = self._stub_class(channel)

    def _server_call(self, rpc_func, request, response_class):
        """
        Call a server function via the RPC mechanism. The method handles server-side
        logic, forwarding the call to the attached server. If no server is attached,
        an error is logged, and an exception is raised.

        Args:
            rpc_func: The RPC function to be called. Expected to be a callable representing
                the server-side procedure.
            request: The request object constructed for the RPC call. Contains all the
                necessary data to process the request.
            response_class: The class of the response object that the RPC call will return.

        Raises:
            GrpcAccessException: Raised when an attempt is made to call a service
                without an attached server.
        """
        if self._server is not None:
            return self._server.server_call(rpc_func, request, response_class)
        else:
            _logger.error("Attempt to call a service not attached to a server")
            raise GrpcAccessException

    def _server_call_multiple(self, rpc_func, request, response_class):
        """
        Yields responses from a server call for a given gRPC function, request, and response class.

        If the server attribute is available, this method delegates to the server's
        `server_call_multiple` method to yield responses. If the server is not attached,
        it logs an error and raises a GrpcAccessException.

        Parameters:
            rpc_func
                The RPC function to be called.
            request
                The request object to be sent to the server.
            response_class
                The class representing the type of response expected from the server.

        Yields:
            Response objects of type `response_class` returned by the `rpc_func` execution
            on the server.

        Raises:
            GrpcAccessException
                Indicates an attempt was made to call a service without a server being attached.
        """
        if self._server is not None:
            for response in self._server.server_call_multiple(rpc_func, request, response_class):
                yield response
        else:
            _logger.error("attempt to call a service not attached to a server")
            raise GrpcAccessException

    def server_state(self):
        return self._server.state
