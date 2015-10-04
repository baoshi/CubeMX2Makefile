#!/usr/bin/env python

import sys
import re
import shutil
import os.path
from string import Template
from xml.etree import ElementTree as ET


C2M_ERR_SUCCESS             =  0
C2M_ERR_INVALID_COMMANDLINE = -1
C2M_ERR_LOAD_TEMPLATE       = -2
C2M_ERR_NO_PROJECT          = -3
C2M_ERR_PROJECT_FILE        = -4
C2M_ERR_IO                  = -5
C2M_ERR_NEED_UPDATE         = -6

# STM32 part to compiler flag mapping
mcu_cflags = {}
mcu_cflags[re.compile('STM32(F|L)0')] = '-mthumb -mcpu=cortex-m0'
mcu_cflags[re.compile('STM32(F|L)1')] = '-mthumb -mcpu=cortex-m3'
mcu_cflags[re.compile('STM32(F|L)2')] = '-mthumb -mcpu=cortex-m3'
mcu_cflags[re.compile('STM32(F|L)3')] = '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=softfp'
mcu_cflags[re.compile('STM32(F|L)4')] = '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=softfp'
mcu_cflags[re.compile('STM32(F|L)7')] = '-mthumb -mcpu=cortex-m7 -mfpu=fpv4-sp-d16 -mfloat-abi=softfp'

if len(sys.argv) != 2:
    sys.stderr.write("\r\nSTM32CubeMX project to Makefile V1.5\r\n")
    sys.stderr.write("-==================================-\r\n")
    sys.stderr.write("Written by Baoshi <mail\x40ba0sh1.com> on 2015-10-03\r\n")
    sys.stderr.write("Copyright www.ba0sh1.com\r\n")
    sys.stderr.write("Apache License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>\r\n")
    sys.stderr.write("Updated for STM32CubeMX Version 4.10.1 http://www.st.com/stm32cube\r\n")
    sys.stderr.write("Usage:\r\n")
    sys.stderr.write("  CubeMX2Makefile.py <STM32CubeMX \"Toolchain Folder Location\">\r\n")
    sys.exit(C2M_ERR_INVALID_COMMANDLINE)

# Load template files
app_folder = os.path.dirname(os.path.abspath(sys.argv[0]))
try:
    fd = open(app_folder + os.path.sep + 'CubeMX2Makefile.tpl', 'rb')
    mft = Template(fd.read())
    fd.close()
except:
    sys.stderr.write("Unable to load template file CubeMX2Makefile.tpl\r\n")
    sys.exit(C2M_ERR_LOAD_TEMPLATE)

proj_folder = os.path.abspath(sys.argv[1])
if not os.path.isdir(proj_folder):
    sys.stderr.write("STM32CubeMX \"Toolchain Folder Location\" %s not found\r\n" % proj_folder)
    sys.exit(C2M_ERR_INVALID_COMMANDLINE)

proj_name = os.path.splitext(os.path.basename(proj_folder))[0]
ac6_project = proj_folder + os.path.sep + 'SW4STM32' + os.path.sep + proj_name + ' Configuration' + os.path.sep + '.project'
ac6_cproject = proj_folder + os.path.sep + 'SW4STM32' + os.path.sep + proj_name + ' Configuration' + os.path.sep + '.cproject'
if not (os.path.isfile(ac6_project) and os.path.isfile(ac6_cproject)):
    sys.stderr.write("SW4STM32 project not found, use STM32CubeMX to generate a SW4STM32 project first\r\n")
    sys.exit(C2M_ERR_NO_PROJECT)

# .project file
try:
    tree = ET.parse(ac6_project)
    root = tree.getroot()
except Exception, e:
    sys.stderr.write("Error: cannot parse SW4STM32 .project file: %s\r\n" % ac6_project)
    sys.exit(C2M_ERR_PROJECT_FILE)
nodes = root.findall('linkedResources/link[type=\'1\']/location')
sources = []
for node in nodes:
    sources.append(re.sub(r'^PARENT-2-PROJECT_LOC/', '', node.text))
sources=list(set(sources))
sources.sort()
c_sources = 'C_SOURCES ='
asm_sources = 'ASM_SOURCES ='
for source in sources:
    ext = os.path.splitext(source)[1]
    if ext == '.c':
        c_sources += ' \\\n  ' + source
    elif ext == '.s':
        asm_sources = asm_sources + ' \\\n  ' + source
    else:
        sys.stderr.write("Unknow source file type: %s\r\n" % source)
        sys.exit(-5)

# .cproject file
try:
    tree = ET.parse(ac6_cproject)
    root = tree.getroot()
except Exception, e:
    sys.stderr.write("Error: cannot parse SW4STM32 .cproject file: %s\r\n" % ac6_cproject)
    sys.exit(C2M_ERR_PROJECT_FILE)
# MCU
mcu = ''
ld_mcu = ''
node = root.find('.//toolChain[@superClass="fr.ac6.managedbuild.toolchain.gnu.cross.exe.debug"]/option[@name="Mcu"]')
try:
    value = node.attrib.get('value')
except Exception, e:
    sys.stderr.write("No target MCU defined\r\n")
    sys.exit(C2M_ERR_PROJECT_FILE)
for pattern, option in mcu_cflags.items():
    if pattern.match(value):
        mcu = option
ld_mcu = mcu
# special case for M7, needs to be linked as M4
if ('m7' in ld_mcu):
    ld_mcu = mcu_cflags[re.compile('STM32(F|L)4')]
if (mcu == '' or ld_mcu == ''):
    sys.stderr.write("Unknown MCU\r\n, please contact author for an update of this utility\r\n")
    sys.stderr.exit(C2M_ERR_NEED_UPDATE)
# AS include
as_includes = 'AS_INCLUDES ='
nodes = root.findall('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.assembler"]/option[@valueType="includePath"]/listOptionValue')
first = 1
for node in nodes:
    value = node.attrib.get('value')
    if (value != ""):
        value = re.sub(r'^..(\\|/)..(\\|/)..(\\|/)', '', value.replace('\\', os.path.sep))
        if first:
            as_includes = 'AS_INCLUDES = -I' + value
            first = 0
        else:
            as_includes += '\nAS_INCLUDES += -I' + value
# AS symbols
as_defs = 'AS_DEFS ='
# C include
c_includes = 'C_INCLUDES ='
nodes = root.findall('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.compiler"]/option[@valueType="includePath"]/listOptionValue')
first = 1
for node in nodes:
    value = node.attrib.get('value')
    if (value != ""):
        value = re.sub(r'^..(\\|/)..(\\|/)..(\\|/)', '', value.replace('\\', os.path.sep))
        if first:
            c_includes = 'C_INCLUDES = -I' + value
            first = 0
        else:
            c_includes += '\nC_INCLUDES += -I' + value
# C symbols
c_defs = 'C_DEFS ='
nodes = root.findall('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.compiler"]/option[@valueType="definedSymbols"]/listOptionValue')
for node in nodes:
    value = node.attrib.get('value')
    if (value != ""):
        c_defs += ' -D' + re.sub(r'([()])', r'\\\1', value)

# Link script
ldscript = 'LDSCRIPT = ' 
node = root.find('.//tool[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.linker"]/option[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.linker.script"]')
try:
    value = node.attrib.get('value')
    value = re.sub(r'^..(\\|/)..(\\|/)..(\\|/)', '', value.replace('\\', os.path.sep))
    value = os.path.basename(value)
except Exception, e:
    sys.stderr.write("No link script defined\r\n")
    sys.exit(C2M_ERR_PROJECT_FILE) 
# copy link script to top level so that user can discard SW4STM32 folder
src = proj_folder + os.path.sep + 'SW4STM32' + os.path.sep + proj_name + ' Configuration' + os.path.sep + value
dst = proj_folder + os.path.sep + value
shutil.copyfile(src, dst)
sys.stdout.write("File created: %s\r\n" % dst)
ldscript += value  

mf = mft.substitute( \
    TARGET = proj_name, \
    MCU = mcu, \
    LDMCU = ld_mcu, \
    C_SOURCES = c_sources, \
    ASM_SOURCES = asm_sources, \
    AS_DEFS = as_defs, \
    AS_INCLUDES = as_includes, \
    C_DEFS = c_defs, \
    C_INCLUDES = c_includes, \
    LDSCRIPT = ldscript)
try:
    fd = open(proj_folder + os.path.sep + 'Makefile', 'wb')
    fd.write(mf)
    fd.close()
except:
    sys.stderr.write("Write Makefile failed\r\n")
    sys.exit(C2M_ERR_IO)
sys.stdout.write("File created: %s\r\n" % (proj_folder + os.path.sep + 'Makefile'))

sys.exit(C2M_ERR_SUCCESS)
