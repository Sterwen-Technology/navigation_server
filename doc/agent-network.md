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


## processes definition section

### ProcessABC

### SystemdProcess(ProcessABC)

### SimpleProcess(ProcessABC)

## AgentService interface





| Name      | Type | Default | Signification                                                          |
|-----------|------|---------|------------------------------------------------------------------------|
| source    | int  | none    | source address to select a device in the logs  (255 select all)        |
| publisher | str  | none    | Name of the publisher dispatching messages (N2KSourceDispatcher class) |
| model_id  | str  | none    | String defining the simulated device for display                       |

