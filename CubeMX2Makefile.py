#!/usr/bin/env python

import sys
import re
import shutil
import os.path
import string
import xml.etree.ElementTree

# Return codes
C2M_ERR_SUCCESS             =  0
C2M_ERR_INVALID_COMMANDLINE = -1
C2M_ERR_LOAD_TEMPLATE       = -2
C2M_ERR_NO_PROJECT          = -3
C2M_ERR_PROJECT_FILE        = -4
C2M_ERR_IO                  = -5
C2M_ERR_NEED_UPDATE         = -6

# Configuration

# STM32 MCU to compiler flags.
mcu_regex_to_cflags_dict = {
    'STM32(F|L)0': '-mthumb -mcpu=cortex-m0',
    'STM32(F|L)1': '-mthumb -mcpu=cortex-m3',
    'STM32(F|L)2': '-mthumb -mcpu=cortex-m3',
    'STM32(F|L)3': '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=softfp',
    'STM32(F|L)4': '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=softfp',
    'STM32(F|L)7': '-mthumb -mcpu=cortex-m7 -mfpu=fpv4-sp-d16 -mfloat-abi=softfp',
}

def main():
    if len(sys.argv) != 2:
        sys.stderr.write("\nSTM32CubeMX project to Makefile V1.6\n")
        sys.stderr.write("-==================================-\n")
        sys.stderr.write("Written by Baoshi <mail\x40ba0sh1.com> on 2015-02-22\n")
        sys.stderr.write("Updated 2015-02-24 for STM32CubeMX 4.13.0 http://www.st.com/stm32cube\n")
        sys.stderr.write("Refer to history.txt for contributors, thanks!\n")
        sys.stderr.write("Apache License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>\n")
        sys.stderr.write("\nUsage:\n")
        sys.stderr.write("  CubeMX2Makefile.py <STM32CubeMX \"Toolchain Folder Location\">\n")
        sys.exit(C2M_ERR_INVALID_COMMANDLINE)

    # Load template files
    app_folder_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    template_file_path = os.path.join(app_folder_path, 'CubeMX2Makefile.tpl')
    try:
        with open(template_file_path, 'r') as f:
            makefile_template = string.Template(f.read())
    except EnvironmentError as e:
        sys.stderr.write("Unable to read template file: {}. Error: {}".format(template_file_path, str(e)))
        sys.exit(C2M_ERR_LOAD_TEMPLATE)

    proj_folder_path = os.path.abspath(sys.argv[1])
    if not os.path.isdir(proj_folder_path):
        sys.stderr.write("STM32CubeMX \"Toolchain Folder Location\" not found: {}\n".format(proj_folder_path))
        sys.exit(C2M_ERR_INVALID_COMMANDLINE)

    proj_name = os.path.splitext(os.path.basename(proj_folder_path))[0]
    ac6_project_path = os.path.join(proj_folder_path, 'SW4STM32', proj_name, '.project')
    ac6_cproject_path = os.path.join(proj_folder_path, 'SW4STM32', proj_name, '.cproject')
    if not (os.path.isfile(ac6_project_path) and os.path.isfile(ac6_cproject_path)):
        sys.stderr.write("SW4STM32 project not found, use STM32CubeMX to generate a SW4STM32 project first\n")
        sys.exit(C2M_ERR_NO_PROJECT)

    # .project file
    try:
        tree = xml.etree.ElementTree.parse(ac6_project_path)
    except Exception as e:
        sys.stderr.write("Unable to parse SW4STM32 .project file: {}. Error: {}\n".format(ac6_project_path, str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    root = tree.getroot()
    nodes = root.findall('linkedResources/link[type=\'1\']/location')
    sources = []
    for mcu_node in nodes:
        sources.append(re.sub(r'^PARENT-2-PROJECT_LOC/', '', mcu_node.text))
    sources=list(set(sources))
    sources.sort()
    c_sources_subst = 'C_SOURCES ='
    asm_sources_subst = 'ASM_SOURCES ='
    for source in sources:
        ext = os.path.splitext(source)[1]
        if ext == '.c':
            c_sources_subst += ' \\\n  ' + source
        elif ext == '.s':
            asm_sources_subst += ' \\\n  ' + source
        else:
            sys.stderr.write("Unknown source file type: {}\n".format(source))
            sys.exit(C2M_ERR_IO)

    # .cproject file
    try:
        tree = xml.etree.ElementTree.parse(ac6_cproject_path)
    except Exception as e:
        sys.stderr.write("Unable to parse SW4STM32 .cproject file: {}. Error: {}\n".format(ac6_cproject_path, str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    root = tree.getroot()

    # MCU
    mcu_node = root.find('.//toolChain[@superClass="fr.ac6.managedbuild.toolchain.gnu.cross.exe.debug"]/option[@name="Mcu"]')
    try:
        mcu_str = mcu_node.attrib.get('value')
    except Exception as e:
        sys.stderr.write("Unable to find target MCU node. Error: {}\n".format(str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    for mcu_regex_pattern, cflags in mcu_regex_to_cflags_dict.items():
        if re.match(mcu_regex_pattern, mcu_str):
            cflags_subst = cflags
            ld_subst = cflags
            break
    else:
        sys.stderr.write("Unknown MCU: {}\n".format(mcu_str))
        sys.stderr.write("Please contact author for an update of this utility.\n")
        sys.stderr.exit(C2M_ERR_NEED_UPDATE)
    
    # Special case for M7, needs to be linked as M4.
    if 'm7' in ld_subst:
        ld_subst = mcu_rx_to_cflags_dict['STM32(F|L)4']

    # AS include
    as_includes_subst = 'AS_INCLUDES ='
    as_include_path_node_list = root.findall('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.assembler"]/option[@valueType="includePath"]/listOptionValue')
    first = True
    for as_include_path_node in as_include_path_node_list:
        as_include_path = as_include_path_node.attrib.get('value')
        if not as_include_path:
            continue
        as_include_path = fix_path(as_include_path)
        if first:
            as_includes_subst = 'AS_INCLUDES = -I' + as_include_path
            first = False
        else:
            as_includes_subst += '\nAS_INCLUDES += -I' + as_include_path

    # AS symbols
    as_defs_subst = 'AS_DEFS ='

    # C include
    c_includes_subst = 'C_INCLUDES ='
    c_include_path_node_list = root.findall('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.compiler"]/option[@valueType="includePath"]/listOptionValue')
    first = True
    for c_include_path_node in c_include_path_node_list:
        c_include_path = c_include_path_node.attrib.get('value')
        if c_include_path:
            c_include_path = fix_path(c_include_path)
            if first:
                c_includes_subst = 'C_INCLUDES = -I' + c_include_path
                first = False
            else:
                c_includes_subst += '\nC_INCLUDES += -I' + c_include_path

    # C symbols
    c_defs_subst = 'C_DEFS ='
    c_def_node_list = root.findall('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.compiler"]/option[@valueType="definedSymbols"]/listOptionValue')
    for c_def_node in c_def_node_list:
        c_def_str = c_def_node.attrib.get('value')
        if c_def_str:
            c_defs_subst += ' -D{}'.format(c_def_str)

    # Link script
    ld_script_node_list = root.find('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.linker"]/option[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.linker.script"]')
    try:
        ld_script_path = ld_script_node_list.attrib.get('value')
    except Exception as e:
        sys.stderr.write("Unable to find link script. Error: {}\n".format(str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    ld_script_name = os.path.basename(ld_script_path)
    ld_script_subst = 'LDSCRIPT = {}'.format(ld_script_name)

    # Copy link script to top level so that user can discard SW4STM32 folder
    src_path = os.path.join(proj_folder_path, 'SW4STM32', proj_name, ld_script_name)
    dst_path = os.path.join(proj_folder_path, ld_script_name)
    shutil.copyfile(src_path, dst_path)
    sys.stdout.write("File created: {}\n".format(dst_path))

    makefile_str = makefile_template.substitute(
        TARGET = proj_name,
        MCU = cflags_subst,
        LDMCU = ld_subst,
        C_SOURCES = c_sources_subst,
        ASM_SOURCES = asm_sources_subst,
        AS_DEFS = as_defs_subst,
        AS_INCLUDES = as_includes_subst,
        C_DEFS = c_defs_subst,
        C_INCLUDES = c_includes_subst,
        LDSCRIPT = ld_script_subst)

    makefile_path = os.path.join(proj_folder_path, 'Makefile')
    try:
        with open(makefile_path, 'wb') as f:
            f.write(makefile_str)
    except EnvironmentError as e:
        sys.stderr.write("Unable to write Makefile: {}. Error: {}\n".format(makefile_path, str(e)))
        sys.exit(C2M_ERR_IO)

    sys.stdout.write("Makefile created: {}\n".format(makefile_path))
    
    sys.exit(C2M_ERR_SUCCESS)


def fix_path(p):
    return re.sub(r'^..(\\|/)..(\\|/)..(\\|/)', '', p.replace('\\', os.path.sep))


if __name__ == '__main__':
    main()
