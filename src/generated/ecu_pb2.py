# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: ecu.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


import generated.nmea2000_pb2 as nmea2000__pb2



DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\tecu.proto\x1a\x0enmea2000.proto\"d\n OpenControllerApplicationRequest\x12\x19\n\x11preferred_address\x18\x01 \x01(\r\x12\r\n\x05title\x18\x02 \x01(\t\x12\x16\n\x0esubscribed_pgn\x18\x03 \x03(\r\"N\n\x15\x43ontrollerApplication\x12\r\n\x05\x63\x61_id\x18\x01 \x01(\r\x12\x16\n\x0e\x61\x63tual_address\x18\x02 \x01(\r\x12\x0e\n\x06status\x18\x03 \x01(\t\">\n\x1c\x43ontrollerApplicationRequest\x12\r\n\x05\x63\x61_id\x18\x01 \x01(\r\x12\x0f\n\x07request\x18\x02 \x01(\t\"<\n\x1b\x43ontrollerApplicationStatus\x12\r\n\x05\x63\x61_id\x18\x01 \x01(\r\x12\x0e\n\x06status\x18\x02 \x01(\t\"G\n\x1c\x43ontrollerApplicationSendMsg\x12\r\n\x05\x63\x61_id\x18\x01 \x01(\r\x12\x18\n\x03msg\x18\x02 \x01(\x0b\x32\x0b.nmea2000pb2\xe3\x01\n\x0c\x45\x43U_NMEA2000\x12\x46\n\x07open_ca\x12!.OpenControllerApplicationRequest\x1a\x16.ControllerApplication\"\x00\x12=\n\x0bgetMessages\x12\x1d.ControllerApplicationRequest\x1a\x0b.nmea2000pb\"\x00\x30\x01\x12L\n\x0bsendMessage\x12\x1d.ControllerApplicationSendMsg\x1a\x1c.ControllerApplicationStatus\"\x00\x62\x06proto3')



_OPENCONTROLLERAPPLICATIONREQUEST = DESCRIPTOR.message_types_by_name['OpenControllerApplicationRequest']
_CONTROLLERAPPLICATION = DESCRIPTOR.message_types_by_name['ControllerApplication']
_CONTROLLERAPPLICATIONREQUEST = DESCRIPTOR.message_types_by_name['ControllerApplicationRequest']
_CONTROLLERAPPLICATIONSTATUS = DESCRIPTOR.message_types_by_name['ControllerApplicationStatus']
_CONTROLLERAPPLICATIONSENDMSG = DESCRIPTOR.message_types_by_name['ControllerApplicationSendMsg']
OpenControllerApplicationRequest = _reflection.GeneratedProtocolMessageType('OpenControllerApplicationRequest', (_message.Message,), {
  'DESCRIPTOR' : _OPENCONTROLLERAPPLICATIONREQUEST,
  '__module__' : 'ecu_pb2'
  # @@protoc_insertion_point(class_scope:OpenControllerApplicationRequest)
  })
_sym_db.RegisterMessage(OpenControllerApplicationRequest)

ControllerApplication = _reflection.GeneratedProtocolMessageType('ControllerApplication', (_message.Message,), {
  'DESCRIPTOR' : _CONTROLLERAPPLICATION,
  '__module__' : 'ecu_pb2'
  # @@protoc_insertion_point(class_scope:ControllerApplication)
  })
_sym_db.RegisterMessage(ControllerApplication)

ControllerApplicationRequest = _reflection.GeneratedProtocolMessageType('ControllerApplicationRequest', (_message.Message,), {
  'DESCRIPTOR' : _CONTROLLERAPPLICATIONREQUEST,
  '__module__' : 'ecu_pb2'
  # @@protoc_insertion_point(class_scope:ControllerApplicationRequest)
  })
_sym_db.RegisterMessage(ControllerApplicationRequest)

ControllerApplicationStatus = _reflection.GeneratedProtocolMessageType('ControllerApplicationStatus', (_message.Message,), {
  'DESCRIPTOR' : _CONTROLLERAPPLICATIONSTATUS,
  '__module__' : 'ecu_pb2'
  # @@protoc_insertion_point(class_scope:ControllerApplicationStatus)
  })
_sym_db.RegisterMessage(ControllerApplicationStatus)

ControllerApplicationSendMsg = _reflection.GeneratedProtocolMessageType('ControllerApplicationSendMsg', (_message.Message,), {
  'DESCRIPTOR' : _CONTROLLERAPPLICATIONSENDMSG,
  '__module__' : 'ecu_pb2'
  # @@protoc_insertion_point(class_scope:ControllerApplicationSendMsg)
  })
_sym_db.RegisterMessage(ControllerApplicationSendMsg)

_ECU_NMEA2000 = DESCRIPTOR.services_by_name['ECU_NMEA2000']
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _OPENCONTROLLERAPPLICATIONREQUEST._serialized_start=29
  _OPENCONTROLLERAPPLICATIONREQUEST._serialized_end=129
  _CONTROLLERAPPLICATION._serialized_start=131
  _CONTROLLERAPPLICATION._serialized_end=209
  _CONTROLLERAPPLICATIONREQUEST._serialized_start=211
  _CONTROLLERAPPLICATIONREQUEST._serialized_end=273
  _CONTROLLERAPPLICATIONSTATUS._serialized_start=275
  _CONTROLLERAPPLICATIONSTATUS._serialized_end=335
  _CONTROLLERAPPLICATIONSENDMSG._serialized_start=337
  _CONTROLLERAPPLICATIONSENDMSG._serialized_end=408
  _ECU_NMEA2000._serialized_start=411
  _ECU_NMEA2000._serialized_end=638
# @@protoc_insertion_point(module_scope)
