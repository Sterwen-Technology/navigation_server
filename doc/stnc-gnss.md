# GNSS module integrated in the STNC800 Platform

## introduction

The STNC platform has a high performance GNSS module from Ublox integrated: a MIA-M10Q.
This is a multi-constellation GNSS with a measurement frequency up to 10Hz.
The chip can be accessed via ttyUSB emulation (ttyUSB0 by default) or I2C.

The NavigationServer platforms provides a set of software components to manage the chip and distribute positioning data in various format/ protocols that are described in the current documentation file.

## Interface with the GNSS IC and communication

### GNSSService

The **GNSSService** component is providing both the communication towards the chip and the presentation of the status via gRPC.
Here are the parameters:

| Name           | Type    | Default      | Signification                                                             |
|----------------|---------|--------------|---------------------------------------------------------------------------|
| device         | string  | /dev/ttyUSB0 | serial device for communication                                           |
| baudrate       | int     | 38400        | data rate, that is the default. Currently no other value is supported     |
| push_to_server | boolean | false        | indicates that the data must be pushed towards another server (see below) | 
| address        | string  | 127.0.0.1    | address of a gRPC server                                                  |
| port           | int     | 4502         | port of the server                                                        |
| trace          | boolean | false        | If true all data from the GNSS chip atr logged in a file                  |

The system is pushing NMEA2000 PGN 129025, 129026, 129029 only. To be extended with PGN 129539 and 129540.

All satellites and fix data are recorded and made available through the gRPC service. The following GNSS systems are supported by the Ublox device:

- GPS-SBAS
- Galileo
- Glonass
- Beidou
- QZSS
- NavIC

However, in Europe, only the 2 first are providing meaning positioning data. By consequence, only data from these 2 constellations are processed systematically.

### interface for the GNSSService

```
message SatellitesInView {
  uint32 svid=1;      // satellite ID
  float elevation=2;  // decimal degrees
  float azimuth=3;    // decimal degrees
  float signal_noise=4;
  float timestamp=5;  // last time seen by the GPS in sec from the Epoch
  uint32 status=6;    // usage in fix
}

message ConstellationStatus {
  string name=1;        // Name of the constellation or GNSS system
  uint32 systemId=2;    // SystemId 
  bool in_fix=3;        // true if the GNSS system is providing a fix
  repeated SatellitesInView satellites=4;
}

message GNSS_Status {
  bool fixed=1;
  float fix_time=2;     //  time stamp seconds since the Epoch
  repeated string constellations=3; // constellations seen
  repeated string const_in_fix=13;  // installations participating to the fix
  float gnss_time=4;    //  time stamp seconds since the Epoch - last time received from GNSS
  uint32 nb_satellites_in_fix=5;
  float latitude=6;     // decimal degree negative south
  float longitude=7;    // decimal degree negative west
  float SOG=8;          // knots
  float COG=9;          // degrees
  float PDOP=10;
  float HDOP=11;
  float VDOP=12;
}

service GNSSService {
  rpc gnss_status(server_cmd) returns (GNSS_Status);
  rpc constellation_details(server_cmd) returns (ConstellationStatus);
}
```

### GNSSCoupler(Coupler)

This coupler collects NMEA0183 sentences from the Ublox module and make them available for a NMEAServer.

| Name         | Type           | Default    | Signification                                  |
|--------------|----------------|------------|------------------------------------------------|
| gnss_service | string         | None       | Name of the associated GNSSService object      |
| formatters   | list of string | [RMC, GGA] | List of the formatters captured by the coupler |

Note: this coupler is only making sense if a NMEAServer is needed to distribute the NMEA0183 data.

## GNSS data handling in message servers

### GNSSInput (NMEA2000Application, GrpcService)

This a gRPC service running under the local gRPC server. That service is receiving NMEA2000 PGN from the GNSSService.
It also behaves as a NMEA2000/CAN Controller Application (J1939 CA) that forward the PGN to the NMEA2000/CAN network to broadcast GNSS positioning data on it.

| Name    | Type   | Default                   | Signification                                                                       |
|---------|--------|---------------------------|-------------------------------------------------------------------------------------|
| address | int    | -1 (allocation requested) | CAN CA (Device) requested address, if absent or -1, will be taken from the ECU pool |
| server  | string | None                      | (inherited parameter from GrpcService): Name of the gRPC associated server          |

The service defined here shall also be declared as application in the CAN controller (NMEA2KActiveController object)

### GNSSInputCoupler(Coupler)

This coupler collects the NMEA2000 messages sent on GNSSInput service and make them available for a NMEA message server
It inherits from all Coupler generic parameters. No conversion to NMEA0183, if NMEA0183 GNSS sentences are needed they can be collected via the GNSSCoupler associated with the GNSSService.

| Name       | Type   | Default | Signification                 |
|------------|--------|---------|-------------------------------|
| gnss_input | string | None    | Name of the GNSSInput service |

