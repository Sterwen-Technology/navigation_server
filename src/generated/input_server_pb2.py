# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: input_server.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


import generated.nmea_messages_pb2 as nmea__messages__pb2



DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x12input_server.proto\x1a\x13nmea_messages.proto2_\n\x0fNMEAInputServer\x12%\n\x06status\x12\x0b.server_cmd\x1a\x0c.server_resp\"\x00\x12%\n\x08pushNMEA\x12\t.nmea_msg\x1a\x0c.server_resp\"\x00\x62\x06proto3')



_NMEAINPUTSERVER = DESCRIPTOR.services_by_name['NMEAInputServer']
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _NMEAINPUTSERVER._serialized_start=43
  _NMEAINPUTSERVER._serialized_end=138
# @@protoc_insertion_point(module_scope)