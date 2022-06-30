# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: console.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\rconsole.proto\"\x94\x02\n\rInstrumentMsg\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x18\n\x10instrument_class\x18\x02 \x01(\t\x12\x15\n\x05state\x18\x03 \x01(\x0e\x32\x06.State\x12.\n\tdev_state\x18\x04 \x01(\x0e\x32\x1b.InstrumentMsg.Device_state\x12\x10\n\x08protocol\x18\x05 \x01(\t\x12\x0e\n\x06msg_in\x18\x06 \x01(\r\x12\x0f\n\x07msg_out\x18\x07 \x01(\r\x12\x0e\n\x06status\x18\x08 \x01(\t\x12\r\n\x05\x65rror\x18\t \x01(\r\"B\n\x0c\x44\x65vice_state\x12\r\n\tNOT_READY\x10\x00\x12\x08\n\x04OPEN\x10\x01\x12\r\n\tCONNECTED\x10\x02\x12\n\n\x06\x41\x43TIVE\x10\x03\"m\n\tServerMsg\x12\n\n\x02id\x18\x01 \x01(\r\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x15\n\x05state\x18\x03 \x01(\x0e\x32\x06.State\x12\x10\n\x08protocol\x18\x04 \x01(\t\x12\x0e\n\x06status\x18\x05 \x01(\t\x12\r\n\x05\x65rror\x18\x06 \x01(\r\"2\n\x07Request\x12\n\n\x02id\x18\x01 \x01(\r\x12\x0b\n\x03\x63md\x18\x02 \x01(\t\x12\x0e\n\x06target\x18\x03 \x01(\t\"&\n\x08Response\x12\n\n\x02id\x18\x01 \x01(\r\x12\x0e\n\x06status\x18\x02 \x01(\t*!\n\x05State\x12\x0b\n\x07STOPPED\x10\x00\x12\x0b\n\x07RUNNING\x10\x01\x32\xe4\x01\n\x11NavigationConsole\x12.\n\x0eGetInstruments\x12\x08.Request\x1a\x0e.InstrumentMsg\"\x00\x30\x01\x12+\n\rGetInstrument\x12\x08.Request\x1a\x0e.InstrumentMsg\"\x00\x12&\n\rInstrumentCmd\x12\x08.Request\x1a\t.Response\"\x00\x12&\n\x0cServerStatus\x12\x08.Request\x1a\n.ServerMsg\"\x00\x12\"\n\tServerCmd\x12\x08.Request\x1a\t.Response\"\x00\x62\x06proto3')

_STATE = DESCRIPTOR.enum_types_by_name['State']
State = enum_type_wrapper.EnumTypeWrapper(_STATE)
STOPPED = 0
RUNNING = 1


_INSTRUMENTMSG = DESCRIPTOR.message_types_by_name['InstrumentMsg']
_SERVERMSG = DESCRIPTOR.message_types_by_name['ServerMsg']
_REQUEST = DESCRIPTOR.message_types_by_name['Request']
_RESPONSE = DESCRIPTOR.message_types_by_name['Response']
_INSTRUMENTMSG_DEVICE_STATE = _INSTRUMENTMSG.enum_types_by_name['Device_state']
InstrumentMsg = _reflection.GeneratedProtocolMessageType('InstrumentMsg', (_message.Message,), {
  'DESCRIPTOR' : _INSTRUMENTMSG,
  '__module__' : 'console_pb2'
  # @@protoc_insertion_point(class_scope:InstrumentMsg)
  })
_sym_db.RegisterMessage(InstrumentMsg)

ServerMsg = _reflection.GeneratedProtocolMessageType('ServerMsg', (_message.Message,), {
  'DESCRIPTOR' : _SERVERMSG,
  '__module__' : 'console_pb2'
  # @@protoc_insertion_point(class_scope:ServerMsg)
  })
_sym_db.RegisterMessage(ServerMsg)

Request = _reflection.GeneratedProtocolMessageType('Request', (_message.Message,), {
  'DESCRIPTOR' : _REQUEST,
  '__module__' : 'console_pb2'
  # @@protoc_insertion_point(class_scope:Request)
  })
_sym_db.RegisterMessage(Request)

Response = _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), {
  'DESCRIPTOR' : _RESPONSE,
  '__module__' : 'console_pb2'
  # @@protoc_insertion_point(class_scope:Response)
  })
_sym_db.RegisterMessage(Response)

_NAVIGATIONCONSOLE = DESCRIPTOR.services_by_name['NavigationConsole']
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _STATE._serialized_start=499
  _STATE._serialized_end=532
  _INSTRUMENTMSG._serialized_start=18
  _INSTRUMENTMSG._serialized_end=294
  _INSTRUMENTMSG_DEVICE_STATE._serialized_start=228
  _INSTRUMENTMSG_DEVICE_STATE._serialized_end=294
  _SERVERMSG._serialized_start=296
  _SERVERMSG._serialized_end=405
  _REQUEST._serialized_start=407
  _REQUEST._serialized_end=457
  _RESPONSE._serialized_start=459
  _RESPONSE._serialized_end=497
  _NAVIGATIONCONSOLE._serialized_start=535
  _NAVIGATIONCONSOLE._serialized_end=763
# @@protoc_insertion_point(module_scope)