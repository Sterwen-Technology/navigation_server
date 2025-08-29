# gRPC secure communication

## Introduction

Having robust communication security is key for services accessible from external clients to prevent any uncontrolled access to the system.
That is particularly important for the Agent and Network services that have wide access to critical resources from the system and are running as root.
gPRC is providing the possibility to run over TLS encrypted communication. But, that is requiring to generate the correct set of certificates for servers and clients before starting operation.

The certificates shall be generated with the server IP addresses on which the TLS communications will run.

The navigation server framework provides the necessary tools to fully setup gRPC over TLS to secure its operations.

