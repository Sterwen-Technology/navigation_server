# Navigation Messages and Data Server toolbox


## Description

The Navigation Messages & Data Server toolbox is a set of software that can run in a distributed environment that collects, process and distributes the data from the boat navigation and power systems.
It is built around several Python application running independently and communicating via various messaging systems. The preferred internal system is based on Google RPC or [gPRC](https://grpc.io/) and [Protobuf](https://protobuf.dev/).
Other possibility is to use NMEA0183 type streams on pseudo NMEA0183 streams encapsulating NMEA2000 (see documentation on NMEA2000 and data formats)

**The toolbox** is focusing on NMEA2000 messages and data, whatever is the format. NMEA0183 messages are also carried but with a minimum of semantic analysis. All applications are using the same Python program.

Based on the configuration file (using YamL syntax), all type of application can be launched:
   - **message server** that acts as a router/concentrator/proxy between NMEA0183/NMEA2000 instrumentation buses with possibly some adhoc interface to be added for energy systems.
   - **energy management** application interfaced with energy system (controllers, MPPT, Converters,...) via NMEA2000 or specific protocols
   - **local agent** this is a local service controlling other services via systemd through commands sent via gRPC, it can also act on the system network and operation (reboot)
   - **data manager** collecting messages and creating datasets like engine start and stop. That is a big area for future development

The above list is not limitative and either by combining existing building block or creating new one in Python, there is no limit on what can be done with our **Navigation Message Server**.

The navigation application is outside the scope of the project and most of the tests have been performed using [Scannav](https://www.scannav.com/).

The toolbox also includes utilities for NMEA2000 that are described in details the NMEA2000 documentation page like the **code_generator** that is generating Protobuf and Python code to process NMEA2000 PGN.

A sample GUI application for the control of the various server is also available [see repository](https://github.com/Sterwen-Technology/navigation_server_gui). It interacts using gRPC with the servers described above. It is based on TkInter.


## Installation
The project is entirely written in Python 3 and has been tested with Python 3.7 - 3.12. It is intended to run on Linux based system. Is has been tested on Debian, Yocto and Ubuntu.
*note: from version 2.1.1 on Python version 3.12 is preferred*
Installation on Windows 10 or 11 is working with some limitations on TCP sockets and no support on Direct CAN connection.

Installations files are available here (tar and wheel): [Sterwen Technology download page](https://sterwen-technology.eu/softwares/)

### Setting up the Python environment and running servers

Please refer to the specific documentation: [Python installation](https://github.com/Sterwen-Technology/navigation_server/blob/V2.2/doc/python_environment.md)



### Running automatically with systemd
In the **system** directory there are sample files to install several services to run the servers automatically. They can be reused, but you have to make sure that the files and locations are corresponding.
The script *install_server* creates 4 services:
- **navigation**: main navigation server for which the 
- **navigation_agent**: host local agent to allow remote control
- **energy**: energy management service (currently limited)
- **navigation_data**: data server, currently mostly some custom processing

So the script is to be customized as well as the service files in the *systemd* subdirectory to match actual installation.

**Warning: starting services in Python requires either to fully work without virtual environment or to be able to refer to the virtual environment from the service file**

Another service is the **can** service that is initializing the CAN bus on boot. It is to be installed to avoid having to initialize manually the CAN upon boot. Again path to scripts is to be modified in the service file.


### Supported hosts hardware
 - ARM 32 bits systems: NXP iMX6 Dual or Quad core running Debian or Yocto; Raspberry Pi2
 - ARM 64 bits systems: RPi3 or 4 (1GB RAM is enough), NXP iMX8 running Debian or Yocto
 - AMD64 systems: Running Ubuntu or Debian
 - AMD64 systems with Windows 10 or 11: partial support only.

### Supported BUS and instrumentation interfaces
 - Shipmodul Miniplex3 using IP host interface (NMEA0183 and NMEA2000)
 - DigitalYacht iKonvert NMEA2000 USB adapter
 - Yacht Devices IP based systems (NMEA2000 and NMEA0183)
 - NMEA0183 over a serial or TCP/IP interface
 - CAN Direct interfaces:
   - PICAN2 HAT on RPi3 or RPi4
   - SolidRun NXP based gateways: Industrial N6 and N8 Compact with CAN interface
 - Victron VE Direct devices (requires a dedicated process to be configured)

The most versatile solution is to use a device that has a direct CAN bus access. In that case, no specific hardware is required and more features can be deployed as this system becomes a real ECU (Electronic Control Unit) that can run one or more Controller Applications (NMEA2000 devices).
The same device could combine some NMEA0183 inputs on serial port(s) and NMEA2000 bus communication.

### Running the system

The first step is to define a configuration file that describe your environment and the processing scheme that is to be implemented in the message_server. Several samples can be found in the **conf** directory. All details for the configuration are in the **Server-Router** documentation file.


### Interactive running

All servers can be started from the command line, they don't require specific permissions behind the read and write access to the interfaces.

### GUI access to the API

A sample GUI has been developed to have a real time control of the various servers via the public API. It has been built using [guizero](https://lawsie.github.io/guizero/). Honestly that looks quick and dirty and this is really like that.
Repository for [Navigation server GUI](https://github.com/Sterwen-Technology/navigation_server_gui)

### Automatic start

For production the system should be run through *systemd*. Services that can be used as samples are provided in the application. And a shell script that install all services at once.

## Documentation

The documentation is located in the *doc* directory.

[message_server documentation](https://github.com/Sterwen-Technology/navigation_server/blob/V2.2/doc/Navigation%20message%20server.md)

[System API](https://github.com/Sterwen-Technology/navigation_server/blob/V2.2/doc/Navigation%20system%20API.md)

[NMEA2000 support](https://github.com/Sterwen-Technology/navigation_server/blob/V2.2/doc/NMEA2000.md)


## Development

The Protobuf files can be modified if needed or by generation of new NMEA2000 supporting messages (see NMEA2000 support), however, the output of the Protobuf compiler into Python needs to be adjusted. This is a known limitation of the grpcio compiler.
To overcome the problem a specific Python script has been developed (mod_pb2.py) as well as a convenience shell script (gen_proto) that generates the Python files from the protobuf ones.


## Support

For any problem encountered, please open an issue in this GitHub repository.

## Roadmap
The current stable version is V2.2. Documentation is aligned on this version.

The version 2.2 is focusing on installation and import optimization

## Contributing

All contributions welcome. 

## Authors and acknowledgment
Laurent Carré - [Sterwen Technology](http://www.sterwen-technology.eu). 

## License
Eclipse Public License 2.0. for all development from Sterwen Technology
GNU Lesser GPL v3.0 for Python-can
Apache License 2.0 for grpc

## Project status
Under development.

