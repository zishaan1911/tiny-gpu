"""The Tiny GPU board: every part and every connection, in one place.

The schematic (schematic.py) and the PCB (board.py) are both generated from this, so they
can't disagree. FPGA pin numbers must match board.pcf.

Circuit, following the FT2232H datasheet, Lattice's iCE40 UltraPlus hardware checklist, and the
open-source iCEBreaker board that uses the same chips:
  USB-C (5 V) -> AMS1117 -> 3.3 V -> AP2112K -> 1.2 V FPGA core
  FT2232H channel A: programs the SPI flash (iceprog), holds the FPGA in reset while it does
  FT2232H channel B: 1 Mbaud UART between the laptop and the GPU
  iCE40UP5K: loads its bitstream from the flash at power-up, runs the GPU
  VGA: 4-bit resistor DAC per colour into the monitor's 75 ohm inputs, plus H/V sync
"""

# FPGA pins (iCE40UP5K-SG48). Mirrors board.pcf.
FPGA_PINS = {
    "CLK_12M": 35,
    "UART_RX": 6,    # FPGA receives: FT2232H BDBUS0 (TXD)
    "UART_TX": 9,    # FPGA sends:    FT2232H BDBUS1 (RXD)
    "LED_N": 11,
    # VGA in pin order round the chip's corner (red at the bottom of the right edge, sync at the
    # left end of the top edge). Pins 32-36 stay free: the 3.3 V pin 33 and the clock pin 35 need
    # the room for their own via and trace.
    "VGA_R0": 25, "VGA_R1": 26, "VGA_R2": 27, "VGA_R3": 28,
    "VGA_G0": 31, "VGA_G1": 37, "VGA_G2": 38, "VGA_G3": 42,
    "VGA_B0": 43, "VGA_B1": 44, "VGA_B2": 45, "VGA_B3": 46,
    "VGA_HS": 47, "VGA_VS": 48,
}

# Binary-weighted DAC: bit 3 (MSB) gets the smallest resistor. All four bits high into 75 ohm
# gives 3.3 V * 75 / (75 + 510||1k||2k||3.9k) = 0.72 V, VGA's full scale of 0.7 V.
DAC = {3: "510", 2: "1k", 1: "2k", 0: "3.9k"}

parts = []


def part(ref, lib_id, value, footprint, pins, mpn="", lcsc="", note="", unit_count=1, bom=True):
    parts.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint, pins=pins,
                      mpn=mpn, lcsc=lcsc, note=note, units=unit_count, bom=bom))


R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"


def res(ref, value, a, b, note=""):
    part(ref, "Device:R", value, R0603, {"1": a, "2": b}, note=note)


def cap(ref, value, a, b="GND", big=False):
    part(ref, "Device:C", value, C0805 if big else C0603, {"1": a, "2": b})


# USB-C, ESD, power ----------------------------------------------------------------------

part("J1", "Connector:USB_C_Receptacle_USB2.0_14P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", {
    "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "SH": "GND",
    "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
    "A5": "CC1", "B5": "CC2",
    "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM",
}, mpn="HRO TYPE-C-31-M-12", lcsc="C165948")
# 5.1k on each CC pin: tells the laptop's port this is a USB device wanting default power.
res("R1", "5.1k", "CC1", "GND")
res("R2", "5.1k", "CC2", "GND")
part("U1", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", {
    "1": "USB_DP", "6": "USB_DP", "3": "USB_DM", "4": "USB_DM", "2": "GND", "5": "VBUS",
}, mpn="USBLC6-2SC6", lcsc="C7519")

part("U2", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", {
    "1": "GND", "2": "+3V3", "3": "VBUS",
}, mpn="AMS1117-3.3", lcsc="C6186")
cap("C1", "10u", "VBUS", big=True)
cap("C2", "22u", "+3V3", big=True)

part("U3", "Regulator_Linear:AP2112K-1.2", "AP2112K-1.2", "Package_TO_SOT_SMD:SOT-23-5", {
    "1": "+3V3", "2": "GND", "3": "+3V3", "4": None, "5": "+1V2",
}, mpn="AP2112K-1.2TRG1")
cap("C3", "1u", "+3V3")
cap("C4", "10u", "+1V2", big=True)

# The PLL gets its own filtered 1.2 V: 100 ohm, 10 uF and 100 nF (Lattice TN1252).
res("R3", "100", "+1V2", "VCCPLL")
cap("C5", "10u", "VCCPLL", big=True)
cap("C6", "100n", "VCCPLL")

part("D1", "Device:LED", "green", LED0603, {"1": "LED_PWR_K", "2": "+3V3"}, note="power")
res("R4", "1k", "LED_PWR_K", "GND")

# Power flags tell the ERC where each supply comes from.
for i, net in enumerate(["VBUS", "GND"], 1):
    part(f"#FLG0{i}", "power:PWR_FLAG", "PWR_FLAG", "", {"1": net}, bom=False)

# FT2232H USB bridge ---------------------------------------------------------------------

ft = {
    "OSCI": "FT_OSCI", "OSCO": "FT_OSCO",
    "VPHY": "+3V3", "VPLL": "+3V3", "VREGIN": "+3V3", "VCCIO": "+3V3",
    "VREGOUT": "FT_1V8", "VCORE": "FT_1V8",
    "REF": "FT_REF", "DM": "USB_DM", "DP": "USB_DP",
    "TEST": "GND", "GND": "GND", "AGND": "GND", "~{RESET}": "FT_RESET_N",
    "EECS": "EE_CS", "EECLK": "EE_CLK", "EEDATA": "EE_DATA",
    # Channel A, MPSSE: the flash and the FPGA's configuration pins, as iceprog expects them.
    "ADBUS0": "FLASH_SCK", "ADBUS1": "FLASH_MOSI", "ADBUS2": "FLASH_MISO", "ADBUS4": "FLASH_CS_N",
    "ADBUS6": "FPGA_CDONE", "ADBUS7": "FPGA_CRESET_N",
    # Channel B, UART.
    "BDBUS0": "UART_RX", "BDBUS1": "UART_TX",
}
part("U4", "Interface_USB:FT2232HL", "FT2232HL", "Package_QFP:LQFP-64_10x10mm_P0.5mm", ft,
     mpn="FT2232HL-REEL", note="pins by name; unlisted pins are left open")
part("Y1", "Device:Crystal_GND24", "12MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", {
    "1": "FT_OSCI", "3": "FT_OSCO", "2": "GND", "4": "GND",
}, mpn="X322512MSB4SI", lcsc="C9002")
cap("C7", "18p", "FT_OSCI")
cap("C8", "18p", "FT_OSCO")
res("R5", "12k 1%", "FT_REF", "GND")
res("R6", "10k", "FT_RESET_N", "+3V3")
cap("C9", "4.7u", "FT_1V8", big=True)
for i, n in enumerate(["FT_1V8", "FT_1V8", "FT_1V8", "+3V3", "+3V3", "+3V3", "+3V3", "+3V3", "+3V3"]):
    cap(f"C{10 + i}", "100n", n)
cap("C19", "4.7u", "+3V3", big=True)

# Configuration EEPROM for the FT2232H (name, serial number, channel modes).
part("U5", "Memory_EEPROM:93LCxxB", "93LC56B", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", {
    "1": "EE_CS", "2": "EE_CLK", "3": "EE_DATA", "4": "EE_DO", "5": "GND", "6": None, "7": None, "8": "+3V3",
}, mpn="93LC56BT-I/SN")
res("R7", "2.2k", "EE_DO", "EE_DATA")
res("R8", "10k", "EE_CS", "+3V3")
res("R9", "10k", "EE_CLK", "+3V3")
res("R10", "10k", "EE_DATA", "+3V3")
cap("C20", "100n", "+3V3")

# iCE40 UltraPlus FPGA -------------------------------------------------------------------

fpga = {
    "VCC": "+1V2", "VCCPLL": "VCCPLL",
    "VCCIO_0": "+3V3", "VCCIO_2": "+3V3", "SPI_VCCIO1": "+3V3", "VPP_2V5": "+3V3",
    "GND": "GND",
    "CDONE": "FPGA_CDONE", "~{CRESET}": "FPGA_CRESET_N",
    "IOB_32a_SPI_SO": "FLASH_MOSI", "IOB_34a_SPI_SCK": "FLASH_SCK",
    "IOB_35b_SPI_SS": "FLASH_CS_N", "IOB_33b_SPI_SI": "FLASH_MISO",
}
fpga_numbers = {str(pin): net for net, pin in FPGA_PINS.items()}
part("U6", "FPGA_Lattice:ICE40UP5K-SG48ITR", "iCE40UP5K", "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",
     {**fpga, **{"#" + k: v for k, v in fpga_numbers.items()}},
     mpn="ICE40UP5K-SG48ITR", unit_count=4,
     note="pins by name, or #number for I/O; unlisted pins are left open")
for i, n in enumerate(["+1V2", "+1V2", "+3V3", "+3V3", "+3V3", "+3V3"]):
    cap(f"C{21 + i}", "100n", n)
cap("C27", "10u", "+3V3", big=True)

# Configuration: CRESET and CDONE pulled up; SPI_SS pulled up so the FPGA boots as SPI master.
res("R11", "10k", "FPGA_CRESET_N", "+3V3")
res("R12", "10k", "FPGA_CDONE", "+3V3")
res("R13", "10k", "FLASH_CS_N", "+3V3")
part("SW1", "Switch:SW_Push", "reset", "Button_Switch_SMD:SW_SPST_TL3342", {"1": "FPGA_CRESET_N", "2": "GND"},
     mpn="TL3342F160QG", note="reloads the bitstream")

part("U7", "Memory_Flash:W25Q128JVS", "W25Q128JVS", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm", {
    "1": "FLASH_CS_N", "2": "FLASH_MISO", "3": "FLASH_WP_N", "4": "GND",
    "5": "FLASH_MOSI", "6": "FLASH_SCK", "7": "FLASH_HOLD_N", "8": "+3V3",
}, mpn="W25Q128JVSIQ", lcsc="C97521")
res("R14", "10k", "FLASH_WP_N", "+3V3")
res("R15", "10k", "FLASH_HOLD_N", "+3V3")
cap("C28", "100n", "+3V3")

part("X1", "Oscillator:ASE-xxxMHz", "12MHz", "Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm", {
    "1": "+3V3", "2": "GND", "3": "CLK_12M", "4": "+3V3",
}, mpn="ASE-12.000MHZ-LC-T")
cap("C29", "100n", "+3V3")

part("D2", "Device:LED", "orange", LED0603, {"1": "LED_N", "2": "LED_USER_A"}, note="frame heartbeat")
res("R16", "1k", "+3V3", "LED_USER_A")

# VGA ------------------------------------------------------------------------------------

n = 17
for colour, line in (("R", "VGA_RED"), ("G", "VGA_GREEN"), ("B", "VGA_BLUE")):
    for bit in (3, 2, 1, 0):
        res(f"R{n}", DAC[bit], f"VGA_{colour}{bit}", line, note=f"{colour} bit {bit}")
        n += 1
res(f"R{n}", "100", "VGA_HS", "VGA_HSYNC")
res(f"R{n + 1}", "100", "VGA_VS", "VGA_VSYNC")

part("J2", "Connector:DE15_Socket_HighDensity_MountingHoles", "VGA",
     "Connector_Dsub:DSUB-15-HD_Socket_Horizontal_P2.29x1.90mm_EdgePinOffset3.03mm_Housed_MountingHolesOffset4.94mm", {
    "1": "VGA_RED", "2": "VGA_GREEN", "3": "VGA_BLUE",
    "5": "GND", "6": "GND", "7": "GND", "8": "GND", "10": "GND", "SH": "GND",
    "13": "VGA_HSYNC", "14": "VGA_VSYNC",
    "4": None, "9": None, "11": None, "12": None, "15": None,
}, mpn="DE-15 female, right angle, 3-row HD")

for i in range(1, 5):
    part(f"H{i}", "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", {}, bom=False)
