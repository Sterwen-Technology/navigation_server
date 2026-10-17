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

from navigation_server.couplers import VEDirectMsg, VED_TEXT, VED_CMD_HEX, VED_RESP_HEX
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



class VictronVEDirectDecoderABC:
    '''
    This class is the ABC of VEDirect text decoder
    and implements only common decoding methods
    '''
    def __init__(self):
        self._initialized = False
        self.product_id = None
        self._device_model = None
        self.serial_number = None
        self._transaction_context = None

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

    def set_charger_on(self, coupler):
        if self._transaction_context is not None:
            raise VEDirectException("VE Direct transaction already in progress")
        hex_cmd = encode_charge_control_command(DEVICE_MODE_ON)
        msg = VEDirectMsg(hex_cmd, VED_CMD_HEX)
        self._transaction_context = (HEX_COMMAND_SET, 0x0200)
        coupler.send(msg)

    def set_charger_off(self, coupler):
        if self._transaction_context is not None:
            raise VEDirectException("VE Direct transaction already in progress")
        hex_cmd = encode_charge_control_command(DEVICE_MODE_OFF)
        msg = VEDirectMsg(hex_cmd, VED_CMD_HEX)
        self._transaction_context = (HEX_COMMAND_SET, 0x0200)
        coupler.send(msg)

    def response_handling(self, response):
        command = response.get('response_code')
        if command is None:
            _logger.warning(f"Received response without response_id: {response}")
            return
        register_id = response.get('register_id')
        if register_id is None:
            _logger.warning(f"Received response without register_id: {response}")
            return
        if command != self._transaction_context[0]:
            _logger.warning(f"Received response with unexpected command: {response}")
            return
        if register_id != self._transaction_context[1]:
            _logger.warning(f"Received response with unexpected register_id: {response}")
            return
        self._transaction_context = None




class VictronSmartShuntData (VictronVEDirectDecoderABC):
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

    def set_charger_off(self, coupler):
        _logger.error("set_charger_off not not allowed")

    def set_charger_on(self, coupler):
        _logger.error("set_charger_on not not allowed")

class VictronDC_DC_Data(VictronVEDirectDecoderABC):
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
            # Let's just trace the HEX responseE
            _logger.info(f"HEX message: {msg.msg}")
            result = VEDirectHEXFrame.decode_hex_response(msg.msg)
            if msg.msg_type == VED_RESP_HEX:
                self.response_handling(result)
            formatted_result = VEDirectHEXFrame.print_decoded_response(result)
            _logger.info(f"HEX response decoded: {formatted_result}")
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


class VictronMPPTData(VictronVEDirectDecoderABC):
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


# =============================================================================
# VE.Direct HEX Protocol Encoding and Decoding
# Based on: Orion-XS-HEX-protocol.md and BlueSolar-HEX-protocol.md
# =============================================================================

# VE.Direct HEX Command codes
HEX_COMMAND_PING = 0x1
HEX_COMMAND_GET = 0x7
HEX_COMMAND_SET = 0x8
HEX_COMMAND_RESTART = 0x6
HEX_COMMAND_ENTER_BOOT = 0x0
HEX_COMMAND_APP_VERSION = 0x3
HEX_COMMAND_PRODUCT_ID = 0x4

# VE.Direct HEX Response codes
HEX_RESPONSE_DONE = 0x1
HEX_RESPONSE_CHECKSUM_ERROR = 0x2
HEX_RESPONSE_UNKNOWN = 0x3
HEX_RESPONSE_ERROR = 0x4
HEX_RESPONSE_PING = 0x5
HEX_RESPONSE_GET = 0x7
HEX_RESPONSE_SET = 0x8
HEX_RESPONSE_ASYNC = 0xA

# Common register IDs (same for MPPT and DC-DC)
REGISTER_DEVICE_MODE = 0x0200
REGISTER_DEVICE_STATE = 0x0201
REGISTER_DEVICE_OFF_REASON = 0x0207
REGISTER_PRODUCT_ID = 0x0100
REGISTER_FIRMWARE_VERSION = 0x0102


# VE.Direct HEX Register Definition Table
# Maps register IDs to their properties for proper decoding
# Based on Orion-XS-HEX-protocol.md and BlueSolar-HEX-protocol.md
VE_DIRECT_REGISTER_TABLE = {
    # ============================================================================
    # Product Information Registers
    # ============================================================================
    0x0100: {
        'name': 'Product Id',
        'type': 'un32',
        'scale': 1.0,
        'unit': None,
        'key': 'product_id_hex'
    },
    0x0102: {
        'name': 'Firmware version',
        'type': 'un32',
        'scale': 1.0,
        'unit': None,
        'key': 'firmware_version_hex'
    },
    0x0104: {
        'name': 'Group Id',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'group_id'
    },
    0x010A: {
        'name': 'Serial number',
        'type': 'string',
        'scale': 1.0,
        'unit': None,
        'key': 'serial_number_hex'
    },
    0x010B: {
        'name': 'Model name',
        'type': 'string',
        'scale': 1.0,
        'unit': None,
        'key': 'model_name_hex'
    },
    0x0140: {
        'name': 'Capabilities',
        'type': 'un32',
        'scale': 1.0,
        'unit': None,
        'key': 'capabilities'
    },
    
    # ============================================================================
    # Generic Device Control Registers
    # ============================================================================
    0x0200: {
        'name': 'Device mode',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'device_mode',
        'enum': {
            0: 'OFF',
            1: 'ON',
            3: 'ON_ALT',
            4: 'OFF_ALT'
        }
    },
    0x0201: {
        'name': 'Device state',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'device_state',
        'enum': {
            0: 'NOT_CHARGING',
            2: 'FAULT',
            3: 'BULK',
            4: 'ABSORPTION',
            5: 'FLOAT',
            6: 'STORAGE',
            7: 'MANUAL_EQUALISE',
            11: 'PSU',
            245: 'WAKE_UP',
            246: 'REPEATED_ABSORPTION',
            247: 'AUTO_EQUALISE',
            248: 'BATTERY_SAFE',
            250: 'BLOCKED',
            252: 'EXTERNAL_CONTROL',
            255: 'UNAVAILABLE'
        }
    },
    0x0202: {
        'name': 'Remote control used',
        'type': 'un32',
        'scale': 1.0,
        'unit': None,
        'key': 'remote_control_used'
    },
    0x0205: {
        'name': 'Device off reason',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'device_off_reason'
    },
    0x0207: {
        'name': 'Device off reason (extended)',
        'type': 'un32',
        'scale': 1.0,
        'unit': None,
        'key': 'device_off_reason_extended'
    },
    
    # ============================================================================
    # Battery Settings Registers
    # ============================================================================
    0xEDF0: {
        'name': 'Battery maximum current',
        'type': 'un16',
        'scale': 0.1,
        'unit': 'A',
        'key': 'battery_max_current'
    },
    0xEDF1: {
        'name': 'Battery type',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'battery_type',
        'enum': {
            1: 'DEFAULT',
            2: 'TYPE_1',
            3: 'TYPE_2',
            4: 'TYPE_3',
            5: 'TYPE_4',
            6: 'TYPE_5',
            7: 'TYPE_6',
            8: 'TYPE_7',
            255: 'USER'
        }
    },
    0xEDF2: {
        'name': 'Battery temp. compensation',
        'type': 'sn16',
        'scale': 0.01,
        'unit': 'mV/K',
        'key': 'battery_temp_compensation'
    },
    0xEDF4: {
        'name': 'Battery equalisation voltage',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'battery_equalisation_voltage'
    },
    0xEDF6: {
        'name': 'Battery float voltage',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'battery_float_voltage'
    },
    0xEDF7: {
        'name': 'Battery absorption voltage',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'battery_absorption_voltage'
    },
    0xEDFB: {
        'name': 'Battery absorption time limit',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'hours',
        'key': 'battery_absorption_time_limit'
    },
    0xEDFC: {
        'name': 'Battery bulk time limit',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'hours',
        'key': 'battery_bulk_time_limit'
    },
    0xEDEF: {
        'name': 'Battery voltage',
        'type': 'un8',
        'scale': 1.0,
        'unit': 'V',
        'key': 'battery_voltage_setting'
    },
    0xEDEA: {
        'name': 'Battery voltage setting',
        'type': 'un8',
        'scale': 1.0,
        'unit': 'V',
        'key': 'battery_voltage_setting'
    },
    0xEDEC: {
        'name': 'Battery temperature',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'K',
        'key': 'battery_temperature'
    },
    0xEDE8: {
        'name': 'BMS present',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'bms_present'
    },
    0xEDFE: {
        'name': 'Adaptive mode',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'adaptive_mode'
    },
    0xEDFF: {
        'name': 'Battery safe mode',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'battery_safe_mode'
    },
    
    # ============================================================================
    # Charger Data Registers
    # ============================================================================
    0xED8D: {
        'name': 'Output voltage',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'output_voltage'
    },
    0xED8E: {
        'name': 'Output power',
        'type': 'un32',
        'scale': 0.01,
        'unit': 'W',
        'key': 'output_power'
    },
    0xED8F: {
        'name': 'Output current',
        'type': 'un16',
        'scale': 0.1,
        'unit': 'A',
        'key': 'output_current'
    },
    0xEDBB: {
        'name': 'Input Voltage',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'input_voltage'
    },
    0xEDBC: {
        'name': 'Input power',
        'type': 'un32',
        'scale': 0.01,
        'unit': 'W',
        'key': 'input_power'
    },
    0xEDBD: {
        'name': 'Input current',
        'type': 'un16',
        'scale': 0.1,
        'unit': 'A',
        'key': 'input_current'
    },
    0xD18D: {
        'name': 'Battery voltage (precise)',
        'type': 'sn32',
        'scale': 0.001,
        'unit': 'V',
        'key': 'battery_voltage_precise'
    },
    0xEDDB: {
        'name': 'Charger temperature',
        'type': 'sn16',
        'scale': 0.01,
        'unit': '°C',
        'key': 'charger_temperature'
    },
    0xEDDA: {
        'name': 'Charger error code',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'charger_error'
    },
    
    # ============================================================================
    # Device Function
    # ============================================================================
    0x0206: {
        'name': 'Device function',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'device_function',
        'enum': {
            0: 'CHARGER',
            1: 'PSU'
        }
    },
    
    # ============================================================================
    # Network/Remote Control Registers
    # ============================================================================
    0x2000: {
        'name': 'Charge algorithm version',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'charge_algorithm_version'
    },
    0x2001: {
        'name': 'Charge voltage set-point',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'charge_voltage_setpoint'
    },
    0x2002: {
        'name': 'Battery voltage sense',
        'type': 'un16',
        'scale': 0.01,
        'unit': 'V',
        'key': 'battery_voltage_sense'
    },
    0x2003: {
        'name': 'Battery temperature sense',
        'type': 'sn16',
        'scale': 0.01,
        'unit': '°C',
        'key': 'battery_temperature_sense'
    },
    0x200A: {
        'name': 'Battery charge current',
        'type': 'sn32',
        'scale': 0.001,
        'unit': 'A',
        'key': 'battery_charge_current'
    },
    0x200C: {
        'name': 'Device state (remote)',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'device_state_remote'
    },
    0x200D: {
        'name': 'Network info',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'network_info'
    },
    0x200E: {
        'name': 'Network mode',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'network_mode'
    },
    0x200F: {
        'name': 'Network status register',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'network_status'
    },
    0x2015: {
        'name': 'Charge current limit',
        'type': 'un16',
        'scale': 0.1,
        'unit': 'A',
        'key': 'charge_current_limit'
    },
    
    # ============================================================================
    # Additional Orion XS / MPPT Registers
    # ============================================================================
    0xD18D: {
        'name': 'Battery voltage (precise)',
        'type': 'sn32',
        'scale': 0.001,
        'unit': 'V',
        'key': 'battery_voltage_precise'
    },
    0xEDDB: {
        'name': 'Charger temperature',
        'type': 'sn16',
        'scale': 0.01,
        'unit': '°C',
        'key': 'charger_temperature'
    },
    0xEDDA: {
        'name': 'Charger error code',
        'type': 'un8',
        'scale': 1.0,
        'unit': None,
        'key': 'charger_error'
    },
    0xE000: {
        'name': 'Energy yield (cumulative)',
        'type': 'un32',
        'scale': 0.01,
        'unit': 'kWh',
        'key': 'energy_yield_cumulative'
    },
}


# Type handlers for decoding
VE_DIRECT_TYPE_HANDLERS = {
    'un8': lambda data: int.from_bytes(data, 'little') if data else 0,
    'un16': lambda data: int.from_bytes(data, 'little') if len(data) >= 2 else int.from_bytes(data + b'\x00', 'little'),
    'un24': lambda data: int.from_bytes(data, 'little') if len(data) >= 3 else int.from_bytes(data + b'\x00' * (3 - len(data)), 'little'),
    'un32': lambda data: int.from_bytes(data, 'little') if len(data) >= 4 else int.from_bytes(data + b'\x00' * (4 - len(data)), 'little'),
    'sn8': lambda data: int.from_bytes(data, 'little', signed=True) if data else 0,
    'sn16': lambda data: int.from_bytes(data, 'little', signed=True) if len(data) >= 2 else int.from_bytes(data + b'\x00', 'little', signed=True),
    'sn24': lambda data: int.from_bytes(data, 'little', signed=True) if len(data) >= 3 else int.from_bytes(data + b'\x00' * (3 - len(data)), 'little', signed=True),
    'sn32': lambda data: int.from_bytes(data, 'little', signed=True) if len(data) >= 4 else int.from_bytes(data + b'\x00' * (4 - len(data)), 'little', signed=True),
    'string': lambda data: data.decode('ascii') if data else ''
}

# Device mode values (for REGISTER_DEVICE_MODE)
DEVICE_MODE_OFF = 0x00
DEVICE_MODE_ON = 0x01
DEVICE_MODE_OFF_ALT = 0x04
DEVICE_MODE_ON_ALT = 0x03


class VEDirectHEXException(VEDirectException):
    """Exception raised for VE.Direct HEX protocol errors"""
    pass


class VEDirectHEXFrame:
    """
    Represents a VE.Direct HEX protocol frame.
    
    The frame format is: : [command] [data][data][...] [check]\n
    Where:
    - command is a single nibble (0-F)
    - data is hexadecimal ASCII representation (uppercase)
    - check is a single byte
    - The sum of all ASCII bytes between ':' and check must equal 0x55
    - Numbers are sent in Little Endian format
    """
    
    FRAME_START = ord(':')
    FRAME_END = ord('\n')
    DLE = 0x10  # Data Link Escape, used as alternative frame end in some implementations
    
    @staticmethod
    def calculate_checksum(data_bytes: bytes) -> int:
        """
        Calculate the checksum for VE.Direct HEX protocol.
        
        According to the specification: "The sum of all data bytes and the check must equal 0x55"
        This means: sum(command_value + all_data_byte_values + checksum_value) mod 256 = 0x55
        Therefore: checksum = (0x55 - sum(command + data)) mod 256
        
        The data_bytes are in ASCII hex representation, so we need to decode them to
        their numeric values before calculating the sum.
        
        For example: message "A8DED00380594" means:
        - Command: 'A' = 0x0A
        - Data: 0x8D, 0xED, 0x00, 0x38, 0x05 (from hex pairs "8D", "ED", "00", "38", "05")
        - Checksum: 0x94
        - Sum: 0x0A + 0x8D + 0xED + 0x00 + 0x38 + 0x05 + 0x94 = 0x255
        - 0x255 mod 256 = 0x55 ✓
        
        Args:
            data_bytes: All bytes between the start marker ':' and the checksum (in ASCII hex)
            
        Returns:
            The checksum value as an integer (0-255)
        """
        # Decode ASCII hex bytes to their numeric values
        # For VE.Direct HEX, data is sent in hexadecimal ASCII representation
        # We need to convert hex pairs to their byte values and sum those
        
        try:
            hex_str = data_bytes.decode('ascii')
            # Pad with leading zero if odd length to make pairs
            if len(hex_str) % 2 != 0:
                hex_str = '0' + hex_str
            # Decode hex string to bytes
            decoded_data = bytes.fromhex(hex_str)
            # Sum all byte values
            total = sum(decoded_data)
        except (ValueError, UnicodeDecodeError):
            # If decoding fails, fall back to ASCII byte sum (shouldn't happen with valid messages)
            total = sum(data_bytes)
        
        checksum = (0x55 - total) & 0xFF
        return checksum
    
    @staticmethod
    def to_little_endian_hex(value: int, length: int) -> str:
        """
        Convert a value to little-endian hexadecimal string.
        
        Args:
            value: The integer value to convert
            length: The number of bytes (1, 2, 4, etc.)
            
        Returns:
            Hexadecimal string in little-endian order (uppercase)
        """
        result = []
        for i in range(length):
            byte = (value >> (i * 8)) & 0xFF
            result.append(f"{byte:02X}")
        return ''.join(result)
    
    @staticmethod
    def encode_command(command: int, data_bytes: bytes = b'') -> bytes:
        """
        Encode a VE.Direct HEX command frame.
        
        Args:
            command: The command code (0-15)
            data_bytes: Additional data bytes as ASCII hex string
            
        Returns:
            Complete frame as bytes including start marker, command, data, checksum, and end marker
        """
        if command < 0 or command > 0xF:
            raise VEDirectHEXException(f"Invalid command code: {command}. Must be 0-15.")
        
        # Start building the frame
        frame_parts = []
        
        # Add start marker
        frame_parts.append(bytes([VEDirectHEXFrame.FRAME_START]))
        
        # Add command as ASCII hex nibble
        cmd_byte = f"{command:X}".encode('ascii')
        frame_parts.append(cmd_byte)
        
        # Add data bytes
        frame_parts.append(data_bytes)
        
        # Combine all parts except end marker for checksum calculation
        frame_without_checksum = b''.join(frame_parts)
        
        # Calculate checksum (all bytes between ':' and checksum)
        # Exclude the start marker ':' itself
        checksum_data = frame_without_checksum[1:]  # Skip the ':'
        checksum = VEDirectHEXFrame.calculate_checksum(checksum_data)
        
        # Add checksum as two ASCII hex characters
        checksum_bytes = f"{checksum:02X}".encode('ascii')
        frame_parts.append(checksum_bytes)
        
        # Add end marker
        frame_parts.append(bytes([VEDirectHEXFrame.FRAME_END]))
        
        return b''.join(frame_parts)
    
    @staticmethod
    def build_set_command(register_id: int, value: int, value_type: str = None) -> bytes:
        """
        Build a SET command (command 8) for writing to a register.
        
        Args:
            register_id: The register ID to write to
            value: The value to write
            value_type: The type of the value ('un8', 'un16', 'un32', 'sn8', 'sn16', 'sn32')
                      If None, will be determined from the value
        
        Returns:
            Complete HEX command frame as bytes
        """
        # Determine value type and length if not specified
        if value_type is None:
            if -0x80 <= value < 0x80:
                value_type = 'un8'
                length = 1
            elif -0x8000 <= value < 0x10000:
                value_type = 'un16' if value >= 0 else 'sn16'
                length = 2
            elif -0x80000000 <= value < 0x100000000:
                value_type = 'un32' if value >= 0 else 'sn32'
                length = 4
            else:
                raise VEDirectHEXException(f"Value {value} is too large for VE.Direct HEX protocol")
        else:
            # Map type to length
            type_lengths = {
                'un8': 1, 'sn8': 1,
                'un16': 2, 'sn16': 2,
                'un24': 3, 'sn24': 3,
                'un32': 4, 'sn32': 4
            }
            length = type_lengths.get(value_type)
            if length is None:
                raise VEDirectHEXException(f"Unsupported value type: {value_type}")
        
        # Encode register ID (always uint16 in little-endian)
        reg_hex = VEDirectHEXFrame.to_little_endian_hex(register_id, 2)
        
        # Encode flags (always 0x00 for now)
        flags_hex = "00"
        
        # Encode value in little-endian hex
        # Mask value to the appropriate length
        mask = (1 << (length * 8)) - 1
        masked_value = value & mask
        val_hex = VEDirectHEXFrame.to_little_endian_hex(masked_value, length)
        
        # Build data part: register + flags + value
        data_hex = reg_hex + flags_hex + val_hex
        data_bytes = data_hex.encode('ascii')
        
        # Encode the complete command
        return VEDirectHEXFrame.encode_command(HEX_COMMAND_SET, data_bytes)
    
    @staticmethod
    def build_get_command(register_id: int) -> bytes:
        """
        Build a GET command (command 7) for reading from a register.
        
        Args:
            register_id: The register ID to read from
        
        Returns:
            Complete HEX command frame as bytes
        """
        # Encode register ID (uint16 in little-endian)
        reg_hex = VEDirectHEXFrame.to_little_endian_hex(register_id, 2)
        
        # Encode flags (always 0x00 for now)
        flags_hex = "00"
        
        # Build data part: register + flags
        data_hex = reg_hex + flags_hex
        data_bytes = data_hex.encode('ascii')
        
        # Encode the complete command
        return VEDirectHEXFrame.encode_command(HEX_COMMAND_GET, data_bytes)
    
    @staticmethod
    def decode_response(frame: bytes) -> dict:
        """
        Decode a VE.Direct HEX response frame (expected to be stripped of markers by the coupler).
        
        Frame format: [command_nibble][data_hex_pairs][checksum_hex_pair]
        
        Where:
        - command_nibble: single hex digit (0-F) in ASCII
        - data_hex_pairs: hexadecimal data bytes in ASCII (even number of chars)
        - checksum_hex_pair: two hex digits representing the checksum byte in ASCII
        - The sum of (command_value + all_data_byte_values + checksum_value) mod 256 = 0x55
        
        Note: The frame is expected to be stripped of start (':') and end (\\n or DLE) markers
        by the coupler before being passed to this function.
        
        Args:
            frame: The response frame as bytes (without markers)
            
        Returns:
            Dictionary containing:
            - 'response_code': The response code (int)
            - 'data': The data part as bytes (raw hex bytes, not decoded)
            - 'data_decoded': The data part decoded to numeric bytes
            - 'raw_frame': The original frame
            - 'checksum_valid': Whether the checksum validation passed
        
        Raises:
            VEDirectHEXException: If the frame is invalid
        """
        # Frame is expected to be stripped of markers by the coupler
        # Format: command_nibble + data_hex_pairs + checksum_hex_pair (odd length: 1 + 2N + 2)
        if len(frame) < 3 or len(frame) % 2 == 0:
            raise VEDirectHEXException(f"Invalid frame length: {frame.hex()}")
        
        try:
            hex_str = frame.decode('ascii')
        except UnicodeDecodeError:
            raise VEDirectHEXException(f"Invalid ASCII in frame: {frame.hex()}")
        
        # Extract: command (1 char) + data (even chars) + checksum (2 chars)
        response_code = int(hex_str[0], 16)
        checksum_value = int(hex_str[-2:], 16)
        data_hex = hex_str[1:-2]
        data_bytes = bytes.fromhex(data_hex) if data_hex else b''
        
        # Verify: (response_code + sum(data_bytes) + checksum_value) mod 256 = 0x55
        total = response_code + sum(data_bytes) + checksum_value
        checksum_valid = (total & 0xFF) == 0x55
        
        if not checksum_valid:
            _logger.warning(f"Checksum mismatch: total={total:02X}, frame={frame.hex()}")
        
        return {
            'response_code': response_code,
            'data': data_hex.encode('ascii') if data_hex else b'',
            'data_decoded': data_bytes,
            'raw_frame': frame,
            'checksum_valid': checksum_valid
        }
    
    @staticmethod
    def decode_hex_response(frame: bytes) -> dict:
        """
        Decode a VE.Direct HEX response frame and parse the data according to response type.
        
        For GET, SET, and Async responses (response_code == 7, 8, or 0xA), this will:
        1. Decode the basic frame structure
        2. Identify the register ID from the data
        3. Look up the register type and scale
        4. Decode the value according to the register type
        5. Apply scale if applicable
        
        For other response codes (PING, DONE, ERROR, etc.), only basic frame parsing is performed.
        
        Args:
            frame: The complete response frame as bytes
            
        Returns:
            Dictionary containing:
            - 'response_code': The response code (int)
            - All fields from decode_response()
            - 'register_id': The register ID (for GET/SET/Async responses)
            - 'value': The decoded value (for GET/Async responses)
            - 'flags': Flags byte (for GET/SET/Async responses)
            - Additional fields depending on response type
        """
        result = VEDirectHEXFrame.decode_response(frame)
        response_code = result['response_code']
        data_decoded = result['data_decoded']
        
        parsed = {'response_code': response_code}
        parsed.update(result)
        
        # Parse based on response code
        # GET, SET, and Async messages all have the same format:
        # register_id (2 bytes LE) + flags (1 byte) + value (variable)
        if response_code in (HEX_RESPONSE_GET, HEX_RESPONSE_SET, HEX_RESPONSE_ASYNC):
            if len(data_decoded) < 3:
                _logger.warning(f"GET/SET/Async response too short: {frame.hex()}")
                return parsed
            
            # Extract register ID (first 2 bytes, little-endian)
            register_id = int.from_bytes(data_decoded[:2], 'little')
            flags = data_decoded[2:3][0] if len(data_decoded) >= 3 else 0
            value_data = data_decoded[3:] if len(data_decoded) > 3 else b''
            
            parsed['register_id'] = register_id
            parsed['flags'] = flags
            
            # Look up register info
            register_info = VE_DIRECT_REGISTER_TABLE.get(register_id)
            if register_info:
                value_type = register_info['type']
                scale = register_info.get('scale', 1.0)
                key = register_info.get('key', f'register_{register_id:04X}')
                
                # Decode value based on type
                value = VEDirectHEXFrame._decode_value_by_type(value_data, value_type)
                scaled_value = value * scale
                
                parsed['value'] = scaled_value
                parsed['value_raw'] = value
                parsed['value_type'] = value_type
                parsed['register_name'] = register_info['name']
                parsed['key'] = key
                parsed['scale'] = scale
                
                # Add enum description if available
                if 'enum' in register_info and value in register_info['enum']:
                    parsed['value_description'] = register_info['enum'][value]
            else:
                # Unknown register, store raw value
                parsed['value_raw'] = value_data
                parsed['register_name'] = f'Unknown_0x{register_id:04X}'
        
        else:
            # Other response codes (PING, DONE, ERROR, etc.)
            # Just store the raw data
            if data_decoded:
                parsed['data_value'] = int.from_bytes(data_decoded, 'little') if data_decoded else 0
        
        return parsed
    
    @staticmethod
    def _decode_value_by_type(data: bytes, value_type: str):
        """
        Decode raw bytes to a numeric value based on the type.
        
        Args:
            data: Raw bytes to decode
            value_type: Type string ('un8', 'un16', 'un32', 'sn8', 'sn16', 'sn32', 'string')
            
        Returns:
            Decoded value (int or str)
        """
        handler = VE_DIRECT_TYPE_HANDLERS.get(value_type)
        if handler:
            return handler(data)
        else:
            _logger.warning(f"Unknown value type: {value_type}")
            return int.from_bytes(data, 'little') if data else 0

    @staticmethod
    def print_decoded_response(decoded: dict) -> str:
        """
        Format a decoded HEX response for printing.
        
        Args:
            decoded: Dictionary returned by decode_hex_response()
            
        Returns:
            Formatted string with register ID (hex), description, and value
        """
        lines = []
        
        # Response code
        response_code = decoded.get('response_code')
        if response_code is not None:
            if response_code == HEX_RESPONSE_GET:
                lines.append(f"GET Response")
            elif response_code == HEX_RESPONSE_SET:
                lines.append(f"SET Response")
            elif response_code == 0xA:
                lines.append(f"Async Message")
            elif response_code == HEX_RESPONSE_DONE:
                lines.append(f"DONE Response")
            elif response_code == HEX_RESPONSE_PING:
                lines.append(f"PING Response")
            else:
                lines.append(f"Response Code: 0x{response_code:02X}")
        
        # Register information
        register_id = decoded.get('register_id')
        if register_id is not None:
            register_name = decoded.get('register_name', f'Unknown 0x{register_id:04X}')
            lines.append(f"  Register: 0x{register_id:04X} ({register_name})")
        
        # Flags
        flags = decoded.get('flags')
        if flags is not None:
            lines.append(f"  Flags: 0x{flags:02X}")
        
        # Value
        value = decoded.get('value')
        value_raw = decoded.get('value_raw')
        value_type = decoded.get('value_type')
        value_description = decoded.get('value_description')
        unit = decoded.get('unit')
        scale = decoded.get('scale')
        
        if value is not None:
            if value_type == 'string':
                lines.append(f"  Value: '{value}'")
            elif value_description:
                lines.append(f"  Value: {value} ({value_description})")
            elif unit:
                lines.append(f"  Value: {value} {unit}")
            else:
                lines.append(f"  Value: {value}")
        elif value_raw is not None:
            if isinstance(value_raw, bytes):
                lines.append(f"  Raw Value: {value_raw.hex()}")
            else:
                lines.append(f"  Raw Value: {value_raw}")
        
        # Checksum status
        checksum_valid = decoded.get('checksum_valid')
        if checksum_valid is not None:
            lines.append(f"  Checksum: {'VALID' if checksum_valid else 'INVALID'}")
        
        return '\n'.join(lines)


def encode_charge_control_command(device_mode: int) -> bytes:
    """
    Encode a charge control command (start/stop charging).
    
    This uses the SET command (8) to write to the DEVICE_MODE register (0x0200).
    The command is the same for both MPPT and DC-DC chargers.
    
    Args:
        device_mode: The device mode value to set
                     Use DEVICE_MODE_ON (0x01) or DEVICE_MODE_ON_ALT (0x03) to start
                     Use DEVICE_MODE_OFF (0x00) or DEVICE_MODE_OFF_ALT (0x04) to stop
    
    Returns:
        Complete HEX command frame as bytes
    
    Example:
        To start charging: encode_charge_control_command(DEVICE_MODE_ON)
        To stop charging: encode_charge_control_command(DEVICE_MODE_OFF)
    """
    return VEDirectHEXFrame.build_set_command(REGISTER_DEVICE_MODE, device_mode)


def encode_start_charging_command() -> bytes:
    """
    Encode a command to start charging.
    
    Returns:
        Complete HEX command frame as bytes
    """
    return encode_charge_control_command(DEVICE_MODE_ON)


def encode_stop_charging_command() -> bytes:
    """
    Encode a command to stop charging.
    
    Returns:
        Complete HEX command frame as bytes
    """
    return encode_charge_control_command(DEVICE_MODE_OFF)
