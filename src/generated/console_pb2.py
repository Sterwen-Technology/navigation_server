# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: console.proto
# Protobuf Python Version: 4.25.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


import generated.arguments_pb2 as arguments__pb2

import generated.iso_name_pb2 as iso__name__pb2

import generated.nmea2000_classes_iso_gen_pb2 as nmea2000__classes__iso__gen__pb2



DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\rconsole.proto\x1a\x0f\x61rguments.proto\x1a\x0eiso_name.proto\x1a\x1enmea2000_classes_iso_gen.proto\"\xdd\x02\n\nCouplerMsg\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x15\n\rcoupler_class\x18\x02 \x01(\t\x12\x15\n\x05state\x18\x03 \x01(\x0e\x32\x06.State\x12+\n\tdev_state\x18\x04 \x01(\x0e\x32\x18.CouplerMsg.Device_state\x12\x10\n\x08protocol\x18\x05 \x01(\t\x12\x0e\n\x06msg_in\x18\x06 \x01(\r\x12\x0f\n\x07msg_raw\x18\r \x01(\r\x12\x0f\n\x07msg_out\x18\x07 \x01(\r\x12\x0e\n\x06status\x18\x08 \x01(\t\x12\r\n\x05\x65rror\x18\t \x01(\r\x12\x12\n\ninput_rate\x18\n \x01(\x02\x12\x16\n\x0einput_rate_raw\x18\x0c \x01(\x02\x12\x13\n\x0boutput_rate\x18\x0b \x01(\x02\"B\n\x0c\x44\x65vice_state\x12\r\n\tNOT_READY\x10\x00\x12\x08\n\x04OPEN\x10\x01\x12\r\n\tCONNECTED\x10\x02\x12\n\n\x06\x41\x43TIVE\x10\x03\"l\n\nConnection\x12\x11\n\tremote_ip\x18\x01 \x01(\t\x12\x13\n\x0bremote_port\x18\x02 \x01(\r\x12\x11\n\ttotal_msg\x18\x03 \x01(\r\x12\x10\n\x08msg_rate\x18\x04 \x01(\x02\x12\x11\n\tmax_delay\x18\x05 \x01(\x02\"\xac\x01\n\x06Server\x12\x14\n\x0cserver_class\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x13\n\x0bserver_type\x18\x03 \x01(\t\x12\x0f\n\x07running\x18\x04 \x01(\x08\x12\x16\n\x0enb_connections\x18\x05 \x01(\r\x12\x0c\n\x04port\x18\x06 \x01(\r\x12\x10\n\x08protocol\x18\x08 \x01(\t\x12 \n\x0b\x63onnections\x18\x07 \x03(\x0b\x32\x0b.Connection\"\xb6\x01\n\x13NavigationServerMsg\x12\n\n\x02id\x18\x01 \x01(\r\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x15\n\x05state\x18\x03 \x01(\x0e\x32\x06.State\x12\x0e\n\x06status\x18\x05 \x01(\t\x12\r\n\x05\x65rror\x18\x06 \x01(\r\x12\x0f\n\x07version\x18\x07 \x01(\t\x12\x12\n\nstart_time\x18\x08 \x01(\t\x12\x10\n\x08hostname\x18\n \x01(\t\x12\x18\n\x07servers\x18\t \x03(\x0b\x32\x07.Server\"\xca\x01\n\x0cN2KDeviceMsg\x12\x0f\n\x07\x61\x64\x64ress\x18\x01 \x01(\r\x12\x0f\n\x07\x63hanged\x18\x02 \x01(\x08\x12\x16\n\x0elast_time_seen\x18\x03 \x01(\x02\x12\x1a\n\x08iso_name\x18\x04 \x01(\x0b\x32\x08.ISOName\x12.\n\x13product_information\x18\x05 \x01(\x0b\x32\x11.Pgn126996ClassPb\x12\x34\n\x19\x63onfiguration_information\x18\x06 \x01(\x0b\x32\x11.Pgn126998ClassPb\"Q\n\x07Request\x12\n\n\x02id\x18\x01 \x01(\r\x12\x0b\n\x03\x63md\x18\x02 \x01(\t\x12\x0e\n\x06target\x18\x03 \x01(\t\x12\x1d\n\x06kwargs\x18\x04 \x01(\x0b\x32\r.ArgumentList\"N\n\x08Response\x12\n\n\x02id\x18\x01 \x01(\r\x12\x0e\n\x06status\x18\x02 \x01(\t\x12&\n\x0fresponse_values\x18\x03 \x01(\x0b\x32\r.ArgumentList*0\n\x05State\x12\x0b\n\x07STOPPED\x10\x00\x12\x0b\n\x07RUNNING\x10\x01\x12\r\n\tSUSPENDED\x10\x03\x32\x8a\x02\n\x11NavigationConsole\x12(\n\x0bGetCouplers\x12\x08.Request\x1a\x0b.CouplerMsg\"\x00\x30\x01\x12%\n\nGetCoupler\x12\x08.Request\x1a\x0b.CouplerMsg\"\x00\x12#\n\nCouplerCmd\x12\x08.Request\x1a\t.Response\"\x00\x12\x30\n\x0cServerStatus\x12\x08.Request\x1a\x14.NavigationServerMsg\"\x00\x12\"\n\tServerCmd\x12\x08.Request\x1a\t.Response\"\x00\x12)\n\nGetDevices\x12\x08.Request\x1a\r.N2KDeviceMsg\"\x00\x30\x01\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'console_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
  DESCRIPTOR._options = None
  _globals['_STATE']._serialized_start=1272
  _globals['_STATE']._serialized_end=1320
  _globals['_COUPLERMSG']._serialized_start=83
  _globals['_COUPLERMSG']._serialized_end=432
  _globals['_COUPLERMSG_DEVICE_STATE']._serialized_start=366
  _globals['_COUPLERMSG_DEVICE_STATE']._serialized_end=432
  _globals['_CONNECTION']._serialized_start=434
  _globals['_CONNECTION']._serialized_end=542
  _globals['_SERVER']._serialized_start=545
  _globals['_SERVER']._serialized_end=717
  _globals['_NAVIGATIONSERVERMSG']._serialized_start=720
  _globals['_NAVIGATIONSERVERMSG']._serialized_end=902
  _globals['_N2KDEVICEMSG']._serialized_start=905
  _globals['_N2KDEVICEMSG']._serialized_end=1107
  _globals['_REQUEST']._serialized_start=1109
  _globals['_REQUEST']._serialized_end=1190
  _globals['_RESPONSE']._serialized_start=1192
  _globals['_RESPONSE']._serialized_end=1270
  _globals['_NAVIGATIONCONSOLE']._serialized_start=1323
  _globals['_NAVIGATIONCONSOLE']._serialized_end=1589
# @@protoc_insertion_point(module_scope)
