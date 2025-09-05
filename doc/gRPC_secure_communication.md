# gRPC secure communication

## Introduction

Having robust communication security is key for services accessible from external clients to prevent any uncontrolled access to the system.
That is particularly important for the Agent and Network services that have wide access to critical resources from the system and are running as root.
gPRC is providing the possibility to run over TLS encrypted communication. But, that is requiring to generate the correct set of certificates for servers and clients before starting operation.

The certificates shall be generated with the server IP addresses on which the TLS communications will run.

The navigation server framework provides the necessary tools to fully setup gRPC over TLS to secure its operations.

## Process

1) Generate the Certification authority (CA) key and certificate.
   There is a convenience script 'generate_CA_certificate' that is generating both files. By default, the CA private key will go in the $$HOME/certificates directory, while the certificate will be stored in $NAVIGATION_DATA.
    The CA private key must never be shared, but shall be accessible locally in order to regenerate the servers keys and certificate.
    The CA certificate shall be used by all clients wanting to connect to the system servers.

    **When several computer have to interoperate, the CA key and certificate needs to be shared amongst all of them to allow any client to communicate with all servers.**
    
    File names:

    Private key: nav_ca_key.pem
    
    Certificate: nav_ca_cert.pem

**Note1: Do not forget to share the CA certificate with all clients**

**Note2: CA key and certificate need to generated only once for the whole system, so don't generate them on each server**


2) Create an SSL configuration file (*nav_openssl.cnf* by default) that specifies the interfaces IP addresses that will be used by server with TLS communication channels.
    A template is available in the reference_conf directory, but more conveniently, the NetworkService is able to generate the file automatically each time the network addresses of the interfaces supporting TLS are changing. 
For that, the network configuration file (network_conf.yml) needs to include specific parameters. (see [Network documentation](agent-network.md))
3) Generate the server key and certificate according to SSL configuration file.
    This can be done either via the convenience script "generate_certificate" or automatically by the NetworkService after regeneration of the configuration file.
That operation needs to be performed on every machine running a process (server) each one IP address of one interface has changed.

Even if the NetworkService is able to generate the server certificates automatically, it is still recommended to generate them manually for the first time. This is particularly true if the NetworkManager configuration does not match the target network configuration from the network configuration file.

## Activating gRPC secure communication

The critical server is the navigation_agent that includes both the AgentService and the NetworkService. So it is recommended to activate the gRPC secure communication on the navigation_agent only to start.

Here are the configuration parameters to activate the secure communication:

a) In all servers configuration files add the following global parameter:
*secure_grpc: true*

b) in the navigation_agent configuration file (agent-network.yml) add the following parameters:

*secure_grpc: true* (as for all others)

in the gRPC server section:
*secure: true*

c) to allow the NetworkService to generate the server certificates automatically, add the following parameter to the navigation_agent configuration file:

*ssl_key_dir: /home/laurent/certificates*: Location of the CA key.

CA certificate is expected to be in {config_path}/certificates/nav_ca_cert.pem

In the NetworkService section:

    generate_ssl: true
    restart_ssl: true
    ipv6_ssl: false

These parameters are false by default. *restart_ssl* is used to restart the server after regeneration of the certificates.

*ipv6_ssl* is used to generate the certificates for IPv6 addresses as well.

In the network configuration file (network_conf.yml) for each connection supporting SSL add:
*support_ssl: true*