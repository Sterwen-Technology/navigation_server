#-------------------------------------------------------------------------------
# Name:        victron_interface
# Purpose:     Decoding and encoding of VEdirect messages (Text and HEX)
#
# Author:      Laurent Carré
#
# Created:     4/10/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

from navigation_server.couplers import VEDirectMsg, VED_TEXT
from navigation_server.router_common import copy_protobuf_data
from navigation_server.generated.nmea2000_classes_gen import Pgn127751Class

_logger = logging.getLogger("ShipDataServer." + __name__)


# VE.Direct Protocol PID to Product Name mapping
# Source: VE.Direct Protocol v3.34
# Note: Products marked with * in the source are phased out
VEDIRECT_PID_TABLE = {
    # ========================================================================
    # Battery Monitors (BMV series)
    # ========================================================================
    0x0203: "BMV-700",
    0x0204: "BMV-702",
    0x0205: "BMV-700H",
    0xA381: "BMV-712 Smart",
    0xA382: "BMV-710H Smart",
    0xA383: "BMV-712 Smart Rev2",
    
    # ========================================================================
    # SmartShunt Battery Monitors
    # ========================================================================
    0xA389: "SmartShunt 500A/50mV",
    0xC035: "SmartShunt 500A/50mV",  # added manually
    0xA38A: "SmartShunt 1000A/50mV",
    0xA38B: "SmartShunt 2000A/50mV",
    
    # ========================================================================
    # Legacy BlueSolar MPPT (phased out)
    # ========================================================================
    0x0300: "BlueSolar MPPT 70",
    0xA040: "BlueSolar MPPT 75",
    0xA041: "BlueSolar MPPT 150",
    
    # ========================================================================
    # BlueSolar MPPT Solar Chargers
    # ========================================================================
    0xA042: "BlueSolar MPPT 75/15",
    0xA043: "BlueSolar MPPT 100/15",
    0xA044: "BlueSolar MPPT 100/30",
    0xA045: "BlueSolar MPPT 100/50",
    0xA046: "BlueSolar MPPT 150/70",
    0xA047: "BlueSolar MPPT 150/100",
    0xA049: "BlueSolar MPPT 100/50 rev2",
    0xA04A: "BlueSolar MPPT 100/30 rev2",
    0xA04B: "BlueSolar MPPT 150/35 rev2",
    0xA04C: "BlueSolar MPPT 75/10",
    0xA04D: "BlueSolar MPPT 150/45",
    0xA04E: "BlueSolar MPPT 150/60",
    0xA04F: "BlueSolar MPPT 150/85",
    0xA066: "BlueSolar MPPT 100/20",
    0xA067: "BlueSolar MPPT 100/20 48V",
    0xA06F: "BlueSolar MPPT 150/45 rev2",
    0xA070: "BlueSolar MPPT 150/60 rev2",
    0xA071: "BlueSolar MPPT 150/70 rev2",
    0xA076: "BlueSolar MPPT 100/30 rev3",
    0xA077: "BlueSolar MPPT 100/50 rev3",
    0xA078: "BlueSolar MPPT 150/35 rev3",
    0xA079: "BlueSolar MPPT 75/10 rev2",
    0xA07A: "BlueSolar MPPT 75/15 rev2",
    0xA07B: "BlueSolar MPPT 100/15 rev2",
    0xA07C: "BlueSolar MPPT 75/10 rev3",
    0xA07D: "BlueSolar MPPT 75/15 rev3",
    
    # BlueSolar MPPT VE.Can
    0xA10F: "BlueSolar MPPT VE.Can 150/100",
    0xA112: "BlueSolar MPPT VE.Can 250/70",
    0xA113: "BlueSolar MPPT VE.Can 250/100",
    0xA117: "BlueSolar MPPT VE.Can 150/100 rev2",
    
    # ========================================================================
    # SmartSolar MPPT Solar Chargers
    # ========================================================================
    0xA050: "SmartSolar MPPT 250/100",
    0xA051: "SmartSolar MPPT 150/100",
    0xA052: "SmartSolar MPPT 150/85",
    0xA053: "SmartSolar MPPT 75/15",
    0xA054: "SmartSolar MPPT 75/10",
    0xA055: "SmartSolar MPPT 100/15",
    0xA056: "SmartSolar MPPT 100/30",
    0xA057: "SmartSolar MPPT 100/50",
    0xA058: "SmartSolar MPPT 150/35",
    0xA059: "SmartSolar MPPT 150/100 rev2",
    0xA05A: "SmartSolar MPPT 150/85 rev2",
    0xA05B: "SmartSolar MPPT 250/70",
    0xA05C: "SmartSolar MPPT 250/85",
    0xA05D: "SmartSolar MPPT 250/60",
    0xA05E: "SmartSolar MPPT 250/45",
    0xA05F: "SmartSolar MPPT 100/20",
    0xA060: "SmartSolar MPPT 100/20 48V",
    0xA061: "SmartSolar MPPT 150/45",
    0xA062: "SmartSolar MPPT 150/60",
    0xA063: "SmartSolar MPPT 150/70",
    0xA064: "SmartSolar MPPT 250/85 rev2",
    0xA065: "SmartSolar MPPT 250/100 rev2",
    0xA068: "SmartSolar MPPT 250/60 rev2",
    0xA069: "SmartSolar MPPT 250/70 rev2",
    0xA06A: "SmartSolar MPPT 150/45 rev2",
    0xA06B: "SmartSolar MPPT 150/60 rev2",
    0xA06C: "SmartSolar MPPT 150/70 rev2",
    0xA06D: "SmartSolar MPPT 150/85 rev3",
    0xA06E: "SmartSolar MPPT 150/100 rev3",
    0xA072: "BlueSolar MPPT 150/45 rev3",
    0xA073: "SmartSolar MPPT 150/45 rev3",
    0xA074: "SmartSolar MPPT 75/10 rev2",
    0xA075: "SmartSolar MPPT 75/15 rev2",
    0xA07E: "SmartSolar MPPT 100/30 12V",
    0xA07F: "All-In-1 SmartSolar MPPT 75/15 12V",
    0xA080: "SmartSolar MPPT 250/60 rev3",
    0xA081: "SmartSolar MPPT 250/70 rev3",
    
    # SmartSolar MPPT VE.Can
    0xA102: "SmartSolar MPPT VE.Can 150/70",
    0xA103: "SmartSolar MPPT VE.Can 150/45",
    0xA104: "SmartSolar MPPT VE.Can 150/60",
    0xA105: "SmartSolar MPPT VE.Can 150/85",
    0xA106: "SmartSolar MPPT VE.Can 150/100",
    0xA107: "SmartSolar MPPT VE.Can 250/45",
    0xA108: "SmartSolar MPPT VE.Can 250/60",
    0xA109: "SmartSolar MPPT VE.Can 250/70",
    0xA10A: "SmartSolar MPPT VE.Can 250/85",
    0xA10B: "SmartSolar MPPT VE.Can 250/100",
    0xA10C: "SmartSolar MPPT VE.Can 150/70 rev2",
    0xA10D: "SmartSolar MPPT VE.Can 150/85 rev2",
    0xA10E: "SmartSolar MPPT VE.Can 150/100 rev2",
    0xA114: "SmartSolar MPPT VE.Can 250/70 rev2",
    0xA115: "SmartSolar MPPT VE.Can 250/100 rev2",
    0xA116: "SmartSolar MPPT VE.Can 250/85 rev2",
    
    # ========================================================================
    # Phoenix Inverters (phased out models marked with *)
    # ========================================================================
    0xA201: "Phoenix Inverter 12V 250VA 230V",
    0xA202: "Phoenix Inverter 24V 250VA 230V",
    0xA204: "Phoenix Inverter 48V 250VA 230V",
    0xA211: "Phoenix Inverter 12V 375VA 230V",
    0xA212: "Phoenix Inverter 24V 375VA 230V",
    0xA214: "Phoenix Inverter 48V 375VA 230V",
    0xA221: "Phoenix Inverter 12V 500VA 230V",
    0xA222: "Phoenix Inverter 24V 500VA 230V",
    0xA224: "Phoenix Inverter 48V 500VA 230V",
    0xA231: "Phoenix Inverter 12V 250VA 230V",
    0xA232: "Phoenix Inverter 24V 250VA 230V",
    0xA234: "Phoenix Inverter 48V 250VA 230V",
    0xA239: "Phoenix Inverter 12V 250VA 120V",
    0xA23A: "Phoenix Inverter 24V 250VA 120V",
    0xA23C: "Phoenix Inverter 48V 250VA 120V",
    0xA241: "Phoenix Inverter 12V 375VA 230V",
    0xA242: "Phoenix Inverter 24V 375VA 230V",
    0xA244: "Phoenix Inverter 48V 375VA 230V",
    0xA249: "Phoenix Inverter 12V 375VA 120V",
    0xA24A: "Phoenix Inverter 24V 375VA 120V",
    0xA24C: "Phoenix Inverter 48V 375VA 120V",
    0xA251: "Phoenix Inverter 12V 500VA 230V",
    0xA252: "Phoenix Inverter 24V 500VA 230V",
    0xA254: "Phoenix Inverter 48V 500VA 230V",
    0xA259: "Phoenix Inverter 12V 500VA 120V",
    0xA25A: "Phoenix Inverter 24V 500VA 120V",
    0xA25C: "Phoenix Inverter 48V 500VA 120V",
    0xA261: "Phoenix Inverter 12V 800VA 230V",
    0xA262: "Phoenix Inverter 24V 800VA 230V",
    0xA264: "Phoenix Inverter 48V 800VA 230V",
    0xA269: "Phoenix Inverter 12V 800VA 120V",
    0xA26A: "Phoenix Inverter 24V 800VA 120V",
    0xA26C: "Phoenix Inverter 48V 800VA 120V",
    0xA271: "Phoenix Inverter 12V 1200VA 230V",
    0xA272: "Phoenix Inverter 24V 1200VA 230V",
    0xA274: "Phoenix Inverter 48V 1200VA 230V",
    0xA279: "Phoenix Inverter 12V 1200VA 120V",
    0xA27A: "Phoenix Inverter 24V 1200VA 120V",
    0xA27C: "Phoenix Inverter 48V 1200VA 120V",
    0xA281: "Phoenix Inverter 12V 1600VA 230V",
    0xA282: "Phoenix Inverter 24V 1600VA 230V",
    0xA284: "Phoenix Inverter 48V 1600VA 230V",
    0xA291: "Phoenix Inverter 12V 2000VA 230V",
    0xA292: "Phoenix Inverter 24V 2000VA 230V",
    0xA294: "Phoenix Inverter 48V 2000VA 230V",
    0xA2A1: "Phoenix Inverter 12V 3000VA 230V",
    0xA2A2: "Phoenix Inverter 24V 3000VA 230V",
    0xA2A4: "Phoenix Inverter 48V 3000VA 230V",
    
    # ========================================================================
    # Phoenix Smart IP43 Chargers
    # ========================================================================
    0xA340: "Phoenix Smart IP43 Charger 12V 50A (1+1)",
    0xA341: "Phoenix Smart IP43 Charger 12V 50A (3)",
    0xA342: "Phoenix Smart IP43 Charger 24V 25A (1+1)",
    0xA343: "Phoenix Smart IP43 Charger 24V 25A (3)",
    0xA344: "Phoenix Smart IP43 Charger 12V 30A (1+1)",
    0xA345: "Phoenix Smart IP43 Charger 12V 30A (3)",
    0xA346: "Phoenix Smart IP43 Charger 24V 16A (1+1)",
    0xA347: "Phoenix Smart IP43 Charger 24V 16A (3)",
    
    # ========================================================================
    # DC-DC Converters (Orion XS series)
    # ========================================================================
    0xA3F0: "Orion XS 12V/12V-50A",
    0xA3F1: "Orion XS 1400",
    0xA3F2: "Orion XS 12V/12V-70A",  # added manually
    
    # ========================================================================
    # Cerbo GX and other monitoring devices
    # ========================================================================
    0xA390: "Cerbo GX",
    0xA391: "Cerbo-S GX",
    0xA392: "Venus GX",
    0xA393: "Octo GX",
    0xA394: "CanBus BMS",
}


class VEDirectException(Exception):
    pass


def send_hex_cmd(self, cmd: int, parameters=None):
    # send a VEDirect HEX command
    #
    if 0 < cmd < 10:
        hex_cmd = 0x30 + cmd
    elif cmd < 17:
        hex_cmd = 0x31 + cmd
    else:
        raise VEDirectException("Illegal HEX command")
    # inster the cmd in buffer
    self._hex_send_buffer[1] = hex_cmd
    cmd_size = 2
    # compute initial checksum
    checksum = 0x55 - cmd

    if parameters is not None:
        for length, value in parameters.items():
            bytes_val = value.to_bytes(length, 'big')
            nb_nibble_count = 0
            start = 0
            while nb_nibble_count < length:
                checksum -= (bytes_val[start] * 16) + bytes_val[start + 1]
                start += 2
            encoded_val = bytes_val.hex().upper().encode()
            self._hex_send_buffer[cmd_size:] = encoded_val
            cmd_size += length * 2
    # add checksum in buffer
    hex_checksum = checksum.to_bytes(2, 'big').hex().upper().encode()
    self._hex_send_buffer[cmd_size:] = hex_checksum
    cmd_size += 2
    self._hex_send_buffer[cmd_size] = 0x10


vedirect_fields = {'current': ('I', float, 0.001),
                        'voltage': ('V', float, 0.001),
                        'panel_power': ('PPV', float, 1.0),
                        'product_id':('PID', str, None),
                        'firmware': ('FW', str, None),
                        'serial': ('SER#', str, None),
                        'error': ('ERR', int, 1),
                        'state': ('CS', int, 1),
                        'mppt_state': ('MPPT', int, 1),
                        'day_max_power': ('H21', float, 1.0),  # W
                        'day_power':('H20', float, 10.0)  # Wh
                        }

def value_from_message(msg, field_name):
    ved_field, field_type, coef = vedirect_fields[field_name]
    if field_type is float:
        value = float(msg[ved_field]) * coef
    elif field_type is int:
        value = int(msg[ved_field])
    else:
        value = msg[ved_field]
    return value


class VEHEXType:
    ve_type_definition = {
        "un8": (False, 1),
        "un16": (False, 2),
        "un24": (False, 3),
        "un32": (False, 4),
        "sn16": (True, 2),
        "sn24": (True, 3),
        "sn32": (True, 4),
        "string": (False, -1)
    }

    def __init__(self, ve_type:str):
        self.ve_type = ve_type
        try:
            self._type_def = self.ve_type_definition[ve_type]
        except KeyError:
            raise ValueError("Unknown vedirect type %s" % ve_type)


class VEDirectHEXParam:
    '''
    This class represents a VEDirect HEX parameter
    and implments encoding and decoding the values
    '''
    def __init__(self, register:int, name:str, description:str, v_type, scale: float=1.0):
        pass

class VictronTextDecoderABC:
    '''
    This class is the ABC of VEDirect text decoder
    and implements only common decoding methods
    '''
    def __init__(self):
        self._initialized = False
        self.product_id = None
        self._device_model = None
        self.serial_number = None

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def device_model(self) -> str:
        return self._device_model

    @property
    def firmware_key(self) -> str:
        return 'FW'

    def _process_static(self, value_dict:dict):
        try:
            self.product_id = value_dict['PID']
            self.firmware = value_dict[self.firmware_key]
        except KeyError:
            _logger.error(f"VE direct {self.__class__.__name__} missing required keys in static data: {value_dict.keys()}")
            return
        self.serial_number = value_dict.get('SER#', 'NO_SERIAL#')
        try:
            product_id = int(self.product_id, 16)
            self._device_model = VEDIRECT_PID_TABLE[product_id]
        except KeyError:
            _logger.warning(f'VE Direct Unknown device model: {self.product_id}')
            _logger.debug(f"VE Direct {self.__class__.__name__} Unknown device model {value_dict}")
            self._device_model = 'Unknown'
        self._initialized = True


class VictronSmartShuntData (VictronTextDecoderABC):
    """
    Data structure for Victron SmartShunt battery monitor data
    Attribute names match protobuf field names for compatibility with copy_protobuf_data
    
    The device sends data in 2 consecutive messages:
    - Message 1: Static data (PID, V, VS, I, P, CE, SOC, TTG, Alarm, etc.) + some dynamic
    - Message 2: Historical/dynamic data (H1, H2, H3, H4, H5, H6, H7, H8, H9, H10, etc.)
    
    This class handles both messages and only marks data as complete when both are received.
    """
    def __init__(self):
        # Initialization flag

        super().__init__()
        # Default values for all fields
        # Battery voltage in Volts
        self.voltage = 0.0
        # Battery current in Amps (positive = charge, negative = discharge)
        self.current = 0.0
        # Instantaneous power in Watts
        self.power = 0.0
        # State of Charge in percent
        self.state_of_charge = 0.0
        # Energy variation in Wh
        self.energy_variation = 0.0
        # Auxiliary voltage
        self.auxiliary_voltage = 0.0
        
        # Additional battery information (for BatteryBank protobuf)
        self.min_voltage = 0.0
        self.max_voltage = 0.0
        self.charge_voltage = 0.0
        
        # Other fields
        self.consumed_ah = 0.0
        self.time_to_go = 0.0
        self.alarm = None
        self.last_discharge_voltage = 0.0
        self.total_ah = 0.0
        self.charge_cycles = 0
        self.deepest_discharge = 0.0
        self.last_discharge = 0.0
        # Track which message types have been received
        self._has_message1 = False
        # Timestamp
        self.timestamp = time.monotonic()

    def _process_msg1(self, value_dict):

        try:
            self.alarm = value_dict['Alarm']
            # Dynamic data from message1
            self.voltage = float(value_dict['V']) * 0.001
            self.current = float(value_dict['I']) * 0.001
            self.power = float(value_dict['P'])
            self.state_of_charge = float(value_dict['SOC']) * 0.01
            self.consumed_ah = float(value_dict['CE']) *0.001
            self.time_to_go = float(value_dict['TTG'])
            self.auxiliary_voltage = float(value_dict['VS']) * 0.001
        except KeyError:
            _logger.warning(f'Missing data in battery message 1 {value_dict}')
            raise

    def _process_msg2(self, value_dict):
        try:
            self.min_voltage = float(value_dict['H7']) * 0.001
            self.max_voltage = float(value_dict['H8']) * 0.001
            self.charge_voltage = float(value_dict['H10']) * 0.001
            self.last_discharge_voltage = float(value_dict['H9']) * 0.001
            self.total_ah = float(value_dict['H6']) * 0.001
            self.charge_cycles = int(value_dict['H4'])
            self.deepest_discharge = float(value_dict['H1']) * 0.001
            self.last_discharge = float(value_dict['H2']) * 0.001
        except KeyError:
            _logger.warning(f'Missing data in battery message 2 {value_dict}')
            raise

    
    def process_msg(self, msg: VEDirectMsg) -> bool:
        """Process a message and return True if all data is complete.
        
        Message 1 contains: PID, V, VS, I, P, CE, SOC, TTG, Alarm, FW, SER#, etc.
        Message 2 contains: H1, H2, H3, H4, H5, H6, H7, H8, H9, H10, etc.
        
        Returns True only after both message types have been processed.
        If not initialized and first message is message2, it's ignored.
        """
        if msg.msg_type == VED_TEXT:
            value_dict = msg.msg
        else:
            # right now we don't support HEX mode
            return False

        if not self._initialized:
            if 'PID' in value_dict:
                _logger.debug("VE Direct SmartShunt first message1 detected")
                try:
                    self._process_static(value_dict)
                    self._process_msg1(value_dict)
                except KeyError:
                    return False
                # self._initialized = True
                self._has_message1 = True
                return True
            else:
                return False

        if self._has_message1:
            # we have the message1, so let's go for the 2
            _logger.debug("BatteryService Processing message2")
            if not 'H1' in value_dict:
                _logger.warning("BatteryService Missing H1 in message wrong sequence")
                return False
            else:
                try:
                    self._process_msg2(value_dict)
                except KeyError:
                    return False
                self._has_message1 = False
                self.timestamp = time.monotonic()
                return True
        else:
            _logger.debug("BatteryService processing  message1")
            try:
                self._process_msg1(value_dict)
                self._has_message1 = True
            except KeyError:
                return False
            return False

    def output_pb(self, output_pb):
        """Fill battery_in_out protobuf with current values using copy_protobuf_data"""
        # battery_in_out has: voltage, current, energy_variation, auxiliary_voltage
        copy_protobuf_data(self, output_pb, ('voltage', 'current', 'energy_variation', 'auxiliary_voltage'))

    def output_info_pb(self, output_pb):
        """Fill BatteryBank protobuf with device information using copy_protobuf_data"""
        # BatteryBank fields that we have: voltage, state_of_charge, min_voltage, max_voltage, charge_voltage
        copy_protobuf_data(self, output_pb, ('voltage', 'state_of_charge', 'min_voltage', 'max_voltage', 'charge_voltage'))


class VictronDC_DC_Data(VictronTextDecoderABC):
    """
    Data structure for Victron Orion XS DC-DC charger
    Based on VE.Direct protocol - SmartBuckboost column
    
    Initialize with default values and update via process_msg method
    """
    
    def __init__(self):
        """
        Initialize with default values
        """
        super().__init__()
        # Input side (from alternate battery/alternator)
        self.input_voltage = 0.0  # Input voltage in V
        self.input_current = 0.0  # Input current in A
        self.input_power = 0.0  # Calculated in W
        
        # Output side (to service battery)
        self.output_voltage = 0.0  # Output voltage in V
        self.output_current = 0.0  # Output current in A
        self.output_power = 0.0  # Calculated in W
        
        # Device information
        #self.product_id = 'Unknown'
        #self.firmware = 'Unknown'
        # self.serial = 'Unknown'
        
        # State and error
        self.state = 0  # VE_state
        self.error = 0  # VE_Error
        self.off_reason = 0  # VE_Off_Reason
        
        # Additional Orion XS specific fields
        self.temperature = 0.0  # Temperature in °C
        self.mode = 0  # Operating mode

    @property
    def firmware_key(self) -> str:
        return 'FWE'

    def process_msg(self, msg: VEDirectMsg):
        """
        Process a VE.Direct message and update data
        
        Args:
            msg: VEDirectMsg issued by the Coupler can be either Txt mode or HEX
            
        Returns:
            True when data has been updated
        """
        if msg.msg_type == VED_TEXT:
            value_dict = msg.msg
        else:
            # right now we don't support HEX mode
            return False

        try:
            self.state = int(value_dict['CS'])
            self.input_voltage = float(value_dict['DC_IN_V']) * 0.01  # 0.01 V units to V (Victron Orion XS format)
            if self.state != 0:
            # Input side (from alternate battery/alternator)

                self.input_current = float(value_dict['DC_IN_I']) * 0.1  # 0.1 A units to A (Victron Orion XS format)
                self.input_power =   float(value_dict['DC_IN_P'])# Calculated in W
            else:
                self.input_current = 0.0
                self.input_power = 0.0
        except KeyError as err:
            _logger.error(f"VEDirect DCDC charger decode error: {err} on msg:{msg.printable()}")
            return False

        # Output side (to service battery)

        self.output_voltage = float(value_dict['V']) * 0.001  # 0.001 V units (mV) to V (Victron VE.Direct format)
        self.output_current = float(value_dict['I']) * 0.001  # 0.001 A units (mA) to A (Victron VE.Direct format)
        self.output_power =  float(value_dict['P']) # Calculated in W
        
        # Device information
        if not self.initialized:
            super()._process_static(value_dict)
        
        # State and error
        if 'CS' in value_dict:
            self.state = int(value_dict['CS'])  # VE_state
        if 'ERR' in value_dict:
            self.error = int(value_dict['ERR'])  # VE_Error
        if 'OR' in value_dict:
            self.off_reason = int(value_dict['OR'], 16)  # VE_Off_Reason

        return True

    def running_values_pb(self, running_values_pb):
        """
        Fill protobuf DC_DC_Charger_running_values message with current data
        
        Args:
            running_values_pb: DC_DC_Charger_running_values protobuf message to fill
        """
        running_values_pb.state = self.state
        running_values_pb.error = self.error
        running_values_pb.off_reason = self.off_reason
        running_values_pb.communication_ok = True
        running_values_pb.input_voltage = self.input_voltage
        running_values_pb.input_current = self.input_current
        running_values_pb.input_power = self.input_power
        running_values_pb.output_voltage = self.output_voltage
        running_values_pb.output_current = self.output_current
        running_values_pb.output_power = self.output_power

    def parameters_pb(self, parameters_pb):
        """
        Fill protobuf DC_DC_Charger_Parameters message with device information
        
        Args:
            parameters_pb: DC_DC_Charger_Parameters protobuf message to fill
        """
        parameters_pb.device_label = f"Orion XS {self.serial_number}" if self.serial_number else "Orion XS"
        parameters_pb.device_model = self.product_id if self.product_id else "Unknown"
        parameters_pb.state = self.state
        parameters_pb.error = self.error
        parameters_pb.off_reason = self.off_reason
        parameters_pb.communication_ok = True


class VictronMPPTData(VictronTextDecoderABC):
    """
    Data structure for Victron MPPT solar charger data
    """

    def __init__(self):
        super().__init__()
        self.current = 0.0
        self.voltage = 0.0
        self.panel_voltage = 0.0
        self.panel_power = 0.0
        self.error = 0
        self.state = 0
        self.mppt_state = 0
        self.day_max_power = 0
        self.day_power = 0

    def process_msg(self, msg: VEDirectMsg) -> bool:
        if msg.msg_type != VED_TEXT:
            return False
        value_dict = msg.msg
        if not self.initialized:
            super()._process_static(value_dict)
        try:
            self.current = float(value_dict['I']) * 0.001
            self.voltage = float(value_dict['V']) * 0.001
            self.panel_voltage = float(value_dict['VPV']) * 0.001
            self.panel_power = float(value_dict['PPV'])
            self.error = int(value_dict['ERR'])
            self.state = int(value_dict['CS'])
            self.mppt_state = int(value_dict['MPPT'])
            self.day_max_power = float(value_dict['H21'])
            self.day_power = float(value_dict['H20']) * 10.0
        except KeyError as e:
            _logger.error(f"Missing key in MPPT Vedirect message - suspecting wrong device: {e}")
            return False
        return True

    def output_pb(self, output_pb_v):
        copy_protobuf_data(self, output_pb_v, ('current', 'voltage', 'panel_voltage','panel_power'))

    def output_info_pb(self, output_pb):
        try:
            copy_protobuf_data(self, output_pb, ('product_id', 'firmware', 'serial_number', 'error', 'state', 'mppt_state',
                                                 'day_max_power', 'day_power'))
        except AttributeError as e:
            _logger.error(f"Attribute error filling MPPT output info: {e}")
            return False
        return True

    state_dict = {0: 0, 2: 9, 3: 1, 4: 2, 5: 5, 7: 4, 247: 4}  # correspondence between Victron and NMEA2000 state

    def gen_pgn_127751(self, sid: int):
        # 12/05/2026 (2.8.1) - the PGN is currently wrongly encoded do not use it for now
        # 31/08/2026 (3.0.0) - PGN definition updated
        res = Pgn127751Class()
        res.sequence_id = sid % 256
        res.connection_number = 1
        res.voltage = self.voltage
        res.current = self.current
        return res
