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
    
2) Create an SSL configuration file (*nav_openssl.cnf* by default) that specifies the interfaces IP addresses that will be used by server with TLS communication channels.
    A template is available in the reference_conf directory, but more conveniently, the NetworkService is able to generate the file automatically each time the network addresses of the interfaces supporting TLS are changing. 
For that, the network configuration file (network_conf.yml) needs to include specific parameters. (see [Network documentation](agent-network.md))
3) Generate the server key and certificate according to SSL configuration file.
    This can be done either via the convenience script "generate_certificate" or automatically by the NetworkService after regeneration of the configuration file.
That operation needs to be performed on every machine running a process (server) each one IP address of one interface has changed.