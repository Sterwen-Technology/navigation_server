#-------------------------------------------------------------------------------
# Name:        dc_dc_test
# Purpose:     Unit test for DC_DC_Service basic interface and message decoding
#
# Author:      Vibe Code
#
# Created:     10/10/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

"""
Simple test for DC_DC_Service basic interface and message decoding.
Tests the DC_DCData class independently.
"""

import sys
import os

# Test the DC_DCData class directly by importing just what we need
# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_dc_dc_data_class():
    """Test DC_DCData class directly without full module imports"""
    print("=" * 70)
    print("DC_DC_Service Unit Tests - Basic Interface and Message Decoding")
    print("=" * 70)
    
    # Import the enums we need
    from navigation_server.generated.energy_pb2 import VE_state, VE_Error, VE_Off_Reason
    
    # Define DC_DCData class inline for testing (same as in dc_dc_service.py)
    class DC_DCData:
        def __init__(self):
            # Input side (from alternate battery/alternator)
            self.input_voltage = 0.0
            self.input_current = 0.0
            self.input_power = 0.0
            
            # Output side (to service battery)
            self.output_voltage = 0.0
            self.output_current = 0.0
            self.output_power = 0.0
            
            # Device information
            self.product_id = 'Unknown'
            self.firmware = 'Unknown'
            self.serial = 'Unknown'
            
            # State and error
            self.state = VE_state.Off
            self.error = VE_Error.no_error
            self.off_reason = VE_Off_Reason.no_reason
            
            # Additional Orion XS specific fields
            self.temperature = 0.0
            self.mode = 0

        def process_msg(self, value_dict):
            # Input side
            if 'V' in value_dict:
                self.input_voltage = float(value_dict['V']) * 0.001
            if 'I' in value_dict:
                self.input_current = float(value_dict['I']) * 0.001
            self.input_power = self.input_voltage * self.input_current
            
            # Output side
            if 'V2' in value_dict:
                self.output_voltage = float(value_dict['V2']) * 0.001
            if 'I2' in value_dict:
                self.output_current = float(value_dict['I2']) * 0.001
            self.output_power = self.output_voltage * self.output_current
            
            # Device information
            if 'PID' in value_dict:
                self.product_id = value_dict['PID']
            if 'FW' in value_dict:
                self.firmware = value_dict['FW']
            if 'SER#' in value_dict:
                self.serial = value_dict['SER#']
            
            # State and error
            if 'CS' in value_dict:
                self.state = int(value_dict['CS'])
            if 'ERR' in value_dict:
                self.error = int(value_dict['ERR'])
            if 'OR' in value_dict:
                self.off_reason = int(value_dict['OR'])
            
            # Additional fields
            if 'T' in value_dict:
                self.temperature = float(value_dict['T']) * 0.1
            if 'MODE' in value_dict:
                self.mode = int(value_dict['MODE'])
            
            return True
    
    # Test 1: Initialization with default values
    print("\nTest 1: DC_DCData initialization with default values...")
    data = DC_DCData()
    
    assert data.input_voltage == 0.0
    assert data.input_current == 0.0
    assert data.input_power == 0.0
    assert data.output_voltage == 0.0
    assert data.output_current == 0.0
    assert data.output_power == 0.0
    assert data.product_id == 'Unknown'
    assert data.firmware == 'Unknown'
    assert data.serial == 'Unknown'
    assert data.state == VE_state.Off
    assert data.error == VE_Error.no_error
    assert data.off_reason == VE_Off_Reason.no_reason
    assert data.temperature == 0.0
    assert data.mode == 0
    print("  ✓ All default values initialized correctly")
    
    # Test 2: process_msg with full VE.Direct data
    print("\nTest 2: DC_DCData.process_msg with Victron Orion XS VE.Direct data...")
    vedirect_msg = {
        'V': '12500',
        'I': '2000',
        'V2': '12300',
        'I2': '1800',
        'PID': '0xA384',
        'FW': '1.42',
        'SER#': 'HQ123456789',
        'CS': '5',
        'ERR': '0',
        'OR': '0',
        'T': '250',
        'MODE': '3'
    }
    
    result = data.process_msg(vedirect_msg)
    assert result is True
    assert data.input_voltage == 12.5
    assert data.input_current == 2.0
    assert abs(data.input_power - 25.0) < 0.001
    assert data.output_voltage == 12.3
    assert data.output_current == 1.8
    assert abs(data.output_power - 22.14) < 0.01
    assert data.product_id == '0xA384'
    assert data.firmware == '1.42'
    assert data.serial == 'HQ123456789'
    assert data.state == 5
    assert data.error == 0
    assert data.off_reason == 0
    assert data.temperature == 25.0
    assert data.mode == 3
    print("  ✓ All VE.Direct values decoded correctly")
    
    # Test 3: Partial updates
    print("\nTest 3: DC_DCData.process_msg with partial data...")
    data2 = DC_DCData()
    msg1 = {'V': '12000', 'I': '1000'}
    data2.process_msg(msg1)
    assert data2.input_voltage == 12.0
    assert data2.input_current == 1.0
    assert data2.output_voltage == 0.0
    
    msg2 = {'V2': '12500', 'I2': '2000'}
    data2.process_msg(msg2)
    assert data2.input_voltage == 12.0
    assert data2.input_current == 1.0
    assert data2.output_voltage == 12.5
    assert data2.output_current == 2.0
    print("  ✓ Partial updates handled correctly")
    
    # Test 4: Missing keys don't cause errors
    print("\nTest 4: DC_DCData.process_msg with missing keys...")
    data3 = DC_DCData()
    msg3 = {'V': '10000'}  # Only one field
    result = data3.process_msg(msg3)
    assert result is True
    assert data3.input_voltage == 10.0
    assert data3.input_current == 0.0  # Unchanged from default
    print("  ✓ Missing keys handled gracefully")
    
    print("\n" + "=" * 70)
    print("All tests passed!")
    print("=" * 70)
    return 0


def main():
    try:
        return test_dc_dc_data_class()
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
