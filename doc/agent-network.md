# Agent local sever

## Introduction

The agent local server allows to remotely control all processes involved in the navigation server system. It can also perform basic function on the underlying Linux system like halting or rebooting it.
In addition to its basic features, the agent process can integrate the network remote control features (they can be integrated in a separate server as well, but for the sake of simplicity, it has has been decided to host them along with process control)

The agent local server "navigation_server" is configured the same way as any other server. It is directly implementing the AgentService and NetworkService services.

## AgentService (GrpcService)

The AgentService is a gRPC accessible service that is implementing an interface towards the local system for remote control including:
- Linux system reboot or halt
- systemd services supervision
- navigation server own systemd services

The process must be driven by a **Main** server from a specific class: **AgentTopServer**


### Processes definition section

#### ProcessABC

This is the generic abstract class for all processes. It is not meant to be used directly.

| Name       | Type    | Default | Signification                                                                                   |
|------------|---------|---------|-------------------------------------------------------------------------------------------------|
| name       | str     | none    | internal name of the process                                                                    |
| autostart  | boolean | false   | If true, the process/service is started automatically when the agent starts                     |
| controlled | boolean | false   | If true, the process can be fully controlled by the agent and communicates to the agent service |

#### SystemdProcess(ProcessABC)

This class is used to control systemd services. The services must have been installed on the system separately.

| Name    | Type    | Default | Signification        |
|---------|---------|---------|----------------------|
| service | str     | none    | systemd service name |

#### SimpleProcess(ProcessABC)

This class supports the following processes:
- shell scripts
- python scripts
- other executable types

**Note: This class is not yet implemented**

| Name      | Type   | Default              | Signification                           |
|-----------|--------|----------------------|-----------------------------------------|
| run_path  | str    | none                 | Full path of the process to be executed |
| type      | choice | shell, python, other |                                         |
| arguments | str    |                      |                                         |

### AgentService interface

The agent service is exposing the following methods (rpc). Details of the message structures can be found in the **agent.proto** file.

#### rpc AgentCmd(AgentCmdMsg) returns (AgentResponse) {}

The method addresses processes specific commands.
The command is one of the following:
- status:   returns the status of the target process
- start:    starts the target process(service)
- stop:     stops the target process(service)
- restart:  restarts the target process(service)
- get_port: returns the port number for the gRPC service of the target process
- interrupt: interrupts the target process (send a SIGINT signal)


#### rpc AgentSystemCmd(AgentCmdMsg) returns(AgentResponse) {}

The method addresses system specific commands.
The command is one of the following:
- status:   returns the status of the system
- reboot:   reboots the system
- halt:     halts the system
- navigation_restart: restarts the navigation_agent and all the navigation system processes

#### rpc RegisterProcess(SystemProcessMsg) returns(AgentResponse) {}

The method registers a process to be controlled by the agent. Controlled processes must contact the agent upon start using that method.

#### rpc GetSystemLog(AgentCmdMsg) returns (stream LogLines) {}

This method returns the systemd log for the target service as a stream of log lines.


## NetworkService(GrpcService)

This service is interfacing with NetworkManager to provide the following features:
- network status and configuration
- create and delete connections
- network configuration
- SSL configuration and certificates generation

NetworkService parameters

| Name          | Type    | Default          | Signification                                                                                       |
|---------------|---------|------------------|-----------------------------------------------------------------------------------------------------|
| configuration | str     | network_conf.yml | file defining the network configuration, shall be located in {conf_path}                            |
| generate_ssl  | boolean | false            | If true the SSL configuration file and certificates are generated when network configuration change |
| restart_ssl   | boolean | false            | When true the navigation system is restarted when new certificates are generated                    |
| ipv6_ssl      | boolean | false            | When true SSL configuration is generated also for IPV6                                              |

To configure properly TLS, see the [TLS configuration](gRPC_secure_communication.md) page.


### NetworkService configuration

The configuration is based on 3 entities to be defined:
- Interfaces that are representing the network physical interfaces and corresponding to NetworkManager devices
- Connections that are representing a configuration for one interface(device) type and corresponding to NetworkManager connections
- Network configuration that is representing a network configuration assigning a connection to an interface(device). Each configuration shall specify a connection for each interface.

The network configuration file is a YAML file with the following structure (with example)

```yaml
interfaces:

- ethernet-0:
     device: end0
     type: ethernet

connections:

- eth-0-wan:
   type: ethernet
   description: "Eth port 0 using DHCP"
   function: WAN_INTERFACE
   support_ssl: true

configurations:

- default:
    ethernet-0: eth-0-wan
```

Supported device types:
- ethernet
- wifi
- cellular

Supported function types:
- WAN_INTERFACE:    address acquired by DHCP and default routing through the WAN interface
- LAN_INTERFACE:    fixed address no routing
- LAN_CONTROLLER:   fixed address associated with a DHCP server and NAT routing

There are also some global parameters:
-apply_default_configuration: if true, the default configuration is applied when the network service starts
-applicable_hardware: list of hardware types that are supported by the network service. If empty, all hardware types are supported (currently only STNC8000 is supported)

### NetworkService interface

#### rpc set_configuration(NetworkCommand) returns (NetworkReply) {}

Apply a given configuration or a connection on one interface.
Fields of the message are:
- cmd: 'configuration' or 'connection'
- source: the connection or configuration name
- interface.name: the interface name

return OK or an error message

#### rpc get_configuration(NetworkCommand) returns (NetworkReply) {}

#### rpc get_status(NetworkCommand) returns (NetworkStatus) {}

returns the network status with all interfaces and associated connections
If the cmd is 'update' , the NetworkManager is queried for the status and the reply is updated accordingly

#### rpc set_global_configuration(NetworkCommand) returns (NetworkStatus) {}

Apply a configuration on all interfaces from this configuration

#### rpc interface_command(NetworkCommand) returns (NetworkReply) {}

Send one of these commands to an interface:
- up_connection: put the connection up
- down_connection: put the connection down
- del_connection: delete the connection

