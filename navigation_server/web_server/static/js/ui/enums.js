// Tables de correspondance enum (protobuf) -> nom lisible, partagees par
// les blocs UI et les collectors (battery, mppt, dc_dc).

export { getEnergySourceTypeName };
export { getVeErrorName };
export { getVeMpptName };
export { getVeOffReasonName };
export { getVeStateName };

// Map EnergySource enum values to human-readable type names
const energySourceTypeNames = {
    0: "Battery",
    1: "Solar",
    2: "Alternator",
    3: "AC Charger",
    4: "DC-DC Charger",
    5: "Windmill",
    6: "Hydro Generator",
    7: "AC Generator",
    8: "AC-DC Converter"
};

// Map VE_state enum values to human-readable names
const veStateNames = {
    0: "Off",
    1: "Low Power",
    2: "Fault",
    3: "Bulk",
    4: "Absorption",
    5: "Float",
    6: "Storage",
    7: "Equalize",
    9: "Inverting",
    11: "Power Supply",
    245: "Starting Up",
    246: "Repeated Absorption",
    247: "Auto Equalize",
    248: "Battery Safe",
    252: "External Control"
};

// Map VE_Error enum values to human-readable names
const veErrorNames = {
    0: "No Error",
    2: "Battery Voltage Too High",
    17: "Charger Temperature Too High",
    18: "Charger Over Current",
    19: "Charger Current Reversed",
    20: "Bulk Time Limit Exceeded",
    21: "Current Sensor Issue",
    33: "Input Voltage Too High",
    34: "Input Current Too High"
};

// Map VE_Off_Reason enum values to human-readable names
const veOffReasonNames = {
    0: "No Reason",
    1: "No Input Power",
    2: "Switched Off (Switch)",
    4: "Switched Off (Register)",
    8: "Remote Input",
    0x10: "Protection Active",
    0x20: "PayGo",
    0x40: "BMS",
    0x80: "Engine Shutdown Detection",
    0x81: "Input voltage low",
    0x100: "Analyzing Input Voltage"
};

// Map VE_MPPT enum values to human-readable names
const veMpptNames = {
    0: "MPPT Off",
    1: "Limited",
    2: "Active"
};

function getEnergySourceTypeName(typeValue) {
    return energySourceTypeNames[typeValue] || ("Type " + typeValue);
}

function getVeStateName(stateValue) {
    return veStateNames[stateValue] || ("State " + stateValue);
}

function getVeErrorName(errorValue) {
    return veErrorNames[errorValue] || ("Error " + errorValue);
}

function getVeOffReasonName(reasonValue) {
    return veOffReasonNames[reasonValue] || ("Reason " + reasonValue);
}

function getVeMpptName(mpptValue) {
    return veMpptNames[mpptValue] || ("MPPT " + mpptValue);
}
