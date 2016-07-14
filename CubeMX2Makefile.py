#!/usr/bin/env python

import sys
import re
import shutil
import os
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
    'STM32(F|L)3': '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard',
    'STM32(F|L)4': '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard',
    'STM32(F|L)7': '-mthumb -mcpu=cortex-m7 -mfpu=fpv4-sp-d16 -mfloat-abi=hard',
}

def main():
    
    if len(sys.argv) != 2:
        sys.stderr.write("\nSTM32CubeMX project to Makefile V1.9\n")
        sys.stderr.write("-==================================-\n")
        sys.stderr.write("Initially written by Baoshi <mail\x40ba0sh1.com> on 2015-02-22\n")
        sys.stderr.write("Updated 2016-06-14 for STM32CubeMX 4.15.1 http://www.st.com/stm32cube\n")
        sys.stderr.write("Refer to history.txt for contributors, thanks!\n")
        sys.stderr.write("Apache License 2.0 <http://www.apachstme3w2e.org/licenses/LICENSE-2.0>\n")
        sys.stderr.write("\nUsage:\n")
        sys.stderr.write("  CubeMX2Makefile.py <SW4STM32 project folder>\n")
        sys.exit(C2M_ERR_INVALID_COMMANDLINE)

    # Load template files
    app_folder_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    template_file_path = os.path.join(app_folder_path, 'CubeMX2Makefile.tpl')
    try:
        with open(template_file_path, 'rb') as f:
            makefile_template = string.Template(f.read())
    except EnvironmentError as e:
        sys.stderr.write("Unable to read template file: {}. Error: {}".format(template_file_path, str(e)))
        sys.exit(C2M_ERR_LOAD_TEMPLATE)

    proj_folder_path = os.path.abspath(sys.argv[1])
    if not os.path.isdir(proj_folder_path):
        sys.stderr.write("STM32CubeMX \"Toolchain Folder Location\" not found: {}\n".format(proj_folder_path))
        sys.exit(C2M_ERR_INVALID_COMMANDLINE)

    proj_name = os.path.splitext(os.path.basename(proj_folder_path))[0]
    ac6_project_path = os.path.join(proj_folder_path,'.project')
    ac6_cproject_path = os.path.join(proj_folder_path,'.cproject')
    if not (os.path.isfile(ac6_project_path) and os.path.isfile(ac6_cproject_path)):
        sys.stderr.write("SW4STM32 project not found, use STM32CubeMX to generate a SW4STM32 project first\n")
        sys.exit(C2M_ERR_NO_PROJECT)


    ctx = []

    c_set = {}
    c_set['source_endswith'] = '.c'
    c_set['source_subst'] = 'C_SOURCES ='
    c_set['inc_endswith'] = '.h'
    c_set['inc_subst'] = 'C_INCLUDES ='
    c_set['first'] = True
    c_set['relpath_stored'] = ''
    ctx.append(c_set)

    asm_set = {}
    asm_set['source_endswith'] = '.s'
    asm_set['source_subst'] = 'ASM_SOURCES ='
    asm_set['inc_endswith'] = '.inc'
    asm_set['inc_subst'] = 'AS_INCLUDES ='
    asm_set['first'] = True
    asm_set['relpath_stored'] = ''
    ctx.append(asm_set)

    for path, dirs, files in os.walk(proj_folder_path):
        for file in files:
            for s in ctx:

                if file.endswith(s['source_endswith']):
                    s['source_subst'] += ' \\\n  '
                    relpath = os.path.relpath(path,proj_folder_path)

                    #Split Windows style paths into tokens
                    #Unix style path emit a single token
                    relpath_split = relpath.split('\\')
                    for path_tok in relpath_split:
                        #Last token does not have a trailing slash
                        if path_tok == relpath_split[0]:
                            s['source_subst'] += path_tok
                        else:
                            s['source_subst'] += '/' + path_tok
                    s['source_subst'] += '/' + file

                if file.endswith(s['inc_endswith']):
                    relpath = os.path.relpath(path,proj_folder_path)

                    #only include a path once
                    if relpath != s['relpath_stored']:
                        s['relpath_stored'] = relpath

                        #If this is the first include, we already have the 'C_INCLUDES ='
                        if s['first']:
                            s['first'] = False
                            s['inc_subst'] += ' -I'
                        else:
                            s['inc_subst'] += '\nC_INCLUDES += -I'


                        #Split Windows style paths into tokens
                        #Unix style path emit a single token
                        relpath_split = relpath.split('\\')
                        for path_tok in relpath_split:
                            #Last token does not have a trailing slash
                            if path_tok == relpath_split[0]:
                                s['inc_subst'] += path_tok
                            else:
                                s['inc_subst'] += '/' + path_tok         
                    
    # .cproject file
    try:
        tree = xml.etree.ElementTree.parse(ac6_cproject_path)
    except Exception as e:
        sys.stderr.write("Unable to parse SW4STM32 .cproject file: {}. Error: {}\n".format(ac6_cproject_path, str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    root = tree.getroot()

    # MCU
    mcu_node = root.find('.//toolChain/option[@superClass="fr.ac6.managedbuild.option.gnu.cross.mcu"][@name="Mcu"]')
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

    # AS symbols
    as_defs_subst = 'AS_DEFS ='

    # C symbols
    c_defs_subst = 'C_DEFS ='
    c_def_node_list = root.findall('.//tool/option[@valueType="definedSymbols"]/listOptionValue')
    for c_def_node in c_def_node_list:
        c_def_str = c_def_node.attrib.get('value')
        if c_def_str:
            c_defs_subst += ' -D{}'.format(c_def_str)

    # Link script
    ld_script_node_list = root.find('.//tool/option[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.linker.script"]')
    try:
        ld_script_path = ld_script_node_list.attrib.get('value')
    except Exception as e:
        sys.stderr.write("Unable to find link script. Error: {}\n".format(str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    ld_script_name = os.path.basename(ld_script_path)
    ld_script_subst = 'LDSCRIPT = {}'.format(ld_script_name)

    makefile_str = makefile_template.substitute(
        TARGET = proj_name,
        MCU = cflags_subst,
        LDMCU = ld_subst,
        C_SOURCES = c_set['source_subst'],
        ASM_SOURCES = asm_set['source_subst'],
        AS_DEFS = as_defs_subst,
        AS_INCLUDES = asm_set['inc_subst'],
        C_DEFS = c_defs_subst,
        C_INCLUDES = c_set['inc_subst'],
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
