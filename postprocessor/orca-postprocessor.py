# /usr/bin/python3

import sys
import re
import argparse
from shutil import ReadError
from os import path


def argumentparser():
    """
        ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog=path.basename(__file__),
        description='** IDEX Post Processing Script for Orca Slicer ** \n\r',
        epilog='Result: Rewrites single extruder multimaterial gcode into dual extruder gcode')

    parser.add_argument('input_file', metavar='gcode-files', type=str, nargs='+',
                        help='One or more GCode file(s) to be processed '
                        '- at least one is required.')

    try:
        args = parser.parse_args()
        return args

    except IOError as msg:
        parser.error(str(msg))


def main(args):
    """
        MAIN
    """
    print(args.input_file)

    for sourcefile in args.input_file:
        if path.exists(sourcefile):
            process_gcodefile(args, sourcefile)


def find_m600(lines):
    m600_locations = []
    for line_number in range(len(lines)):
        if lines[line_number].startswith("M600"):
            m600_locations.append(line_number)
    return m600_locations


def update_toolchanges(lines, m600_locations):
    changesDetected = False

    # Rewrite single extruder filament changes into IDEX-macros.
    """
    ex.
    M600
    M106 S0
    T0
    M104 S243 ; set nozzle temperature
    ; Filament gcode
    SET_PRESSURE_ADVANCE ADVANCE=0.03; Override pressure advance value
    ; printing object Logo id:0 copy 0
    EXCLUDE_OBJECT_END NAME=Logo_id_0_copy_0
    EXCLUDE_OBJECT_START NAME=Logo_id_0_copy_0
    G1 X250.28 Y271.914 F21000

    becomes
     0 ; M600
    +1 M106 S0 T0 !!!TODO!!!
    +2 T0 P1 X250.29 Y271.914
    +3 M104 S243 T0
    +4 ; Filament gcode
    +5 SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=0.03; Override pressure advance value
    +6 ; printing object Logo id:0 copy 0
    +7 EXCLUDE_OBJECT_END NAME=Logo_id_0_copy_0
    +8 EXCLUDE_OBJECT_START NAME=Logo_id_0_copy_0
    +9 G1 X250.28 Y271.914 F21000
    """
    for m600_location in m600_locations:
        lines[m600_location] = lines[m600_location].replace("M600", "; M600")

        m106_offset = 0
        active_toolhead = 0
        toolhead_init_x = "X0"
        toolhead_init_y = "Y0"

        if "M106" not in lines[m600_location + 1] and ";_FORCE_RESUME_FAN_SPEED" not in lines[m600_location + 1]:
            m106_offset = -1

        g1_offset = 0
        g1_x_y_regex = "G1 X[0-9]*\\.*[0-9]* Y[0-9]*\\.*[0-9]*"
        g1_x_y_match = re.search(g1_x_y_regex, lines[m600_location+g1_offset])
        while g1_x_y_match is None:
            g1_offset += 1
            g1_x_y_match = re.search(
                g1_x_y_regex, lines[m600_location+g1_offset])

        x_match = re.search("X[0-9]*\\.*[0-9]*",
                            lines[m600_location + g1_offset])
        if x_match:
            toolhead_init_x = x_match.group()

        y_match = re.search("Y[0-9]*\\.*[0-9]*",
                            lines[m600_location + g1_offset])
        if y_match:
            toolhead_init_y = y_match.group()

        if "T0" in lines[m600_location + m106_offset + 2]:
            lines[m600_location + m106_offset + 2] = lines[m600_location +
                                                           m106_offset + 2].replace("T0", f"T0 P1 {toolhead_init_x} {toolhead_init_y}")
            active_toolhead = 0
        elif "T1" in lines[m600_location + m106_offset + 2]:
            lines[m600_location + m106_offset + 2] = lines[m600_location +
                                                           m106_offset + 2].replace("T1", f"T1 P1 {toolhead_init_x} {toolhead_init_y}")
            active_toolhead = 1
        else:
            print("Invalid M600 section. T0/T1 not found.")
            print(lines[m600_location + m106_offset + 2])

        lines[m600_location + m106_offset + 3] = lines[m600_location + m106_offset +
                                                       3].replace("; set nozzle temperature", f"T{active_toolhead}; set nozzle temperature")

        if "SET_PRESSURE_ADVANCE" in lines[m600_location + m106_offset + 5]:
            extruder = "extruder"
            if active_toolhead == 1:
                extruder = "extruder1"
            lines[m600_location + m106_offset + 5] = lines[m600_location + m106_offset +
                                                           5].replace("SET_PRESSURE_ADVANCE", f"SET_PRESSURE_ADVANCE EXTRUDER={extruder}")
        else:
            print(
                "Invalid M600 section. SET_PRESSURE_ADVANCE wasn't where it should've been.")
            print(lines[m600_location + m106_offset + 5])
        changesDetected = True

    return changesDetected


def process_gcodefile(args, sourcefile):
    """
        MAIN Processing.
        To do with ever file from command line.
    """

    # Read the ENTIRE GCode file into memory
    try:
        with open(sourcefile, "r", encoding='UTF-8') as readfile:
            lines = readfile.readlines()
    except ReadError as exc:
        print('FileReadError:' + str(exc))
        sys.exit(1)

    m600_locations = find_m600(lines)

    start_print_line = 0
    for line in range(len(lines)):
        if lines[line].rstrip().startswith("START_PRINT"):
            start_print_line = line
            break

    # Add macro optimization for when only a single toolhead is used.
    if len(m600_locations) < 2:
        lines[start_print_line] = lines[start_print_line].replace(
            "\n", " BOTH_TOOLHEADS=False\n")

    # Fix color references
    lines[start_print_line] = lines[start_print_line].replace(
        "COLOR=#", "COLOR=")
    lines[start_print_line] = lines[start_print_line].replace(
        "COLOR_1=#", "COLOR_1=")

    update_toolchanges(lines, m600_locations)

    writefile = None
    try:
        with open(sourcefile, "w", newline='\n', encoding='UTF-8') as writefile:
            for i, strline in enumerate(lines):
                writefile.write(strline)
    except Exception as exc:
        print("Oops! Something went wrong. " + str(exc))
        sys.exit(1)
    finally:
        writefile.close()
        readfile.close()


ARGS = argumentparser()

main(ARGS)
