##
## Copyright (c) Microsoft. All rights reserved.
## Licensed under the MIT license. See LICENSE file in the project root for full license information.
##
#
#USAGE:
#Add Events: modify <root>src/vm/ClrEtwAll.man
#Look at the Code in  <root>/src/inc/genXplatLttng.py for using subroutines in this file
#

import os 
import xml.dom.minidom as DOM

stdprolog="""
//
// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
//

/******************************************************************

DO NOT MODIFY. AUTOGENERATED FILE.
This file is generated using the logic from <root>/src/scripts/genXplatEventing.py

******************************************************************/
"""

stdprolog_cmake="""
#
#
#******************************************************************

#DO NOT MODIFY. AUTOGENERATED FILE.
#This file is generated using the logic from <root>/src/scripts/genXplatEventing.py

#******************************************************************
"""

lindent = "                  ";
palDataTypeMapping ={
        #constructed types
        "win:null"          :" ",
        "win:Int64"         :"const __int64",
        "win:ULong"         :"const ULONG",
        "win:count"         :"*",
        "win:Struct"        :"const void",
        #actual spec
        "win:GUID"          :"const GUID",
        "win:AnsiString"    :"LPCSTR",
        "win:UnicodeString" :"PCWSTR",
        "win:Double"        :"const double",
        "win:Int32"         :"const signed int",
        "win:Boolean"       :"const BOOL",
        "win:UInt64"        :"const unsigned __int64",
        "win:UInt32"        :"const unsigned int",
        "win:UInt16"        :"const unsigned short",
        "win:UInt8"         :"const unsigned char",
        "win:Pointer"       :"const void*",
        "win:Binary"        :"const BYTE"
        }
# A Template represents an ETW template can contain 1 or more AbstractTemplates
# The AbstractTemplate contains FunctionSignature 
# FunctionSignature consist of FunctionParameter representing each parameter in it's signature

class AbstractTemplate:
    def __init__(self,abstractTemplateName,abstractFnFrame):
        self.abstractTemplateName = abstractTemplateName
        self.AbstractFnFrame      = abstractFnFrame
    

class Template:

    def __init__(self,templateName):
        self.template                  = templateName
        self.allAbstractTemplateTypes  = [] # list of AbstractTemplateNames 
        self.allAbstractTemplateLUT    = {} #dictionary of AbstractTemplate 
    
    def append(self,abstractTemplateName,abstractFnFrame):
        self.allAbstractTemplateTypes.append(abstractTemplateName)
        self.allAbstractTemplateLUT[abstractTemplateName] = AbstractTemplate(abstractTemplateName,abstractFnFrame)

    def getFnFrame(self,abstractTemplateName):
        return self.allAbstractTemplateLUT[abstractTemplateName].AbstractFnFrame

    def getAbstractVarProps(self,abstractTemplateName):
        return self.allAbstractTemplateLUT[abstractTemplateName].AbstractVarProps

    def getFnParam(self,name):
        for subtemplate in self.allAbstractTemplateTypes:
           frame =  self.getFnFrame(subtemplate)
           if frame.getParam(name):
               return frame.getParam(name)
        return None 

class FunctionSignature:

    def __init__(self):
        self.LUT       = {} # dictionary of FunctionParameter 
        self.paramlist = [] # list of parameters to maintain their order in signature

    def append(self,variable,fnparam):
        self.LUT[variable] = fnparam
        self.paramlist.append(variable)

    def getParam(self,variable):
        return self.LUT.get(variable)

    def getLength(self):
        return len(self.paramlist)

class FunctionParameter:

    def __init__(self,winType,name,count,prop):
        self.winType  = winType   #ETW type as given in the manifest
        self.name     = name      #parameter name as given in the manifest
        self.prop     = prop      #any special property as determined by the manifest and developer
        #self.count               #indicates if the parameter is a pointer 
        if  count == "win:null":
            self.count    = "win:null"
        elif count or winType == "win:GUID" or count == "win:count":
        #special case for GUIDS, consider them as structs
            self.count    = "win:count"
        else:
            self.count    = "win:null"


def getTopLevelElementsByTagName(Node,tag):

    dataNodes       = []
    for element in Node.getElementsByTagName(tag):
        if element.parentNode == Node:
            dataNodes.append(element)

    return dataNodes

def bucketizeAbstractTemplates(template,fnPrototypes,var_Dependecies):
    # At this point we have the complete argument list, now break them into chunks of 10 
    # As Abstract Template supports a maximum of 10 arguments
    abstractTemplateName = template;
    subevent_cnt         = 1;
    templateProp         = Template(template)
    abstractFnFrame      = FunctionSignature()

    for variable in fnPrototypes.paramlist:
        for dependency in var_Dependecies[variable]:
            if not abstractFnFrame.getParam(dependency):
                abstractFnFrame.append(dependency,fnPrototypes.getParam(dependency))

            frameCount = abstractFnFrame.getLength()
            if frameCount == 10: 

                templateProp.append(abstractTemplateName,abstractFnFrame)
                abstractTemplateName = template + "_" + str(subevent_cnt)
                subevent_cnt        += 1

                if len(var_Dependecies[variable]) > 1:
                    #check if the frame's dependencies are all present
                    depExists = True
                    for depends in var_Dependecies[variable]:
                        if not abstractFnFrame.getParam(depends):
                            depExists = False
                            break
                    if not depExists:
                        raise ValueError('Abstract Template: '+ abstractTemplateName+ ' does not have all its dependecies in the frame, write required Logic here and test it out, the parameter whose dependency is missing is :'+ variable)
                        #psuedo code:
                        # 1. add a missing dependecies to the frame of the current parameter
                        # 2. Check if the frame has enough space, if there is continue adding missing dependencies
                        # 3. Else Save the current Frame and start a new frame and follow step 1 and 2
                        # 4. Add the current parameter and proceed
                
                #create a new fn frame 
                abstractFnFrame      = FunctionSignature()


    #subevent_cnt == 1 represents argumentless templates
    if abstractFnFrame.getLength() > 0 or subevent_cnt == 1:
        templateProp.append(abstractTemplateName,abstractFnFrame)

    return templateProp

ignoredXmlTemplateAttribes = frozenset(["map","outType"])
usedXmlTemplateAttribes    = frozenset(["name","inType","count", "length"])

def parseTemplateNodes(templateNodes):

    #return values
    allTemplates           = {}

    for templateNode in templateNodes:

        template        = templateNode.getAttribute('tid')
        var_Dependecies = {}
        fnPrototypes    = FunctionSignature()
        dataNodes       = getTopLevelElementsByTagName(templateNode,'data')

        # Validate that no new attributes has been added to manifest
        for dataNode in dataNodes:
            nodeMap = dataNode.attributes
            for attrib in nodeMap.values():
                attrib_name = attrib.name
                if attrib_name not in ignoredXmlTemplateAttribes and attrib_name not in usedXmlTemplateAttribes:
                    raise ValueError('unknown attribute: '+ attrib_name + ' in template:'+ template)
        
        for dataNode in dataNodes:
            variable    = dataNode.getAttribute('name')
            wintype     = dataNode.getAttribute('inType')
                                    
            #count and length are the same
            wincount  = dataNode.getAttribute('count')
            winlength = dataNode.getAttribute('length');

            var_Props = None
            var_dependency = [variable]
            if  winlength:
                if wincount:
                    raise Exception("both count and length property found on: " + variable + "in template: " + template) 
                wincount = winlength

            if (wincount.isdigit() and int(wincount) ==1):
                wincount = ''
            
            if  wincount:
                if (wincount.isdigit()):
                    var_Props = wincount
                elif  fnPrototypes.getParam(wincount): 
                    var_Props = wincount
                    var_dependency.insert(0,wincount)
        
            #construct the function signature

            
            if  wintype == "win:GUID":
                var_Props = "sizeof(GUID)/sizeof(int)"
            
            var_Dependecies[variable] = var_dependency
            fnparam        = FunctionParameter(wintype,variable,wincount,var_Props)
            fnPrototypes.append(variable,fnparam)

        structNodes = getTopLevelElementsByTagName(templateNode,'struct')
       
        count = 0;
        for structToBeMarshalled in structNodes:
            struct_len     = "Arg"+ str(count) + "_Struct_Len_"
            struct_pointer = "Arg"+ str(count) + "_Struct_Pointer_"
            count += 1 

            #populate the Property- used in codegen
            structname   = structToBeMarshalled.getAttribute('name')
            countVarName = structToBeMarshalled.getAttribute('count')

            if not countVarName:
                raise ValueError('Struct '+ structname+ ' in template:'+ template + 'does not have an attribute count')
                
            var_Props                       = countVarName + "*" + struct_len + "/sizeof(int)"
            var_Dependecies[struct_len]     = [struct_len]
            var_Dependecies[struct_pointer] = [countVarName,struct_len,struct_pointer]
            
            fnparam_len            = FunctionParameter("win:ULong",struct_len,"win:null",None)
            fnparam_pointer        = FunctionParameter("win:Struct",struct_pointer,"win:count",var_Props)
            
            fnPrototypes.append(struct_len,fnparam_len)
            fnPrototypes.append(struct_pointer,fnparam_pointer)

        allTemplates[template] = bucketizeAbstractTemplates(template,fnPrototypes,var_Dependecies)
    
    return allTemplates

def generateClrallEvents(eventNodes,allTemplates):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventEnabled
        clrallEvents.append("inline BOOL EventEnabled")
        clrallEvents.append(eventName)
        clrallEvents.append("() {return XplatEventLogger::IsEventLoggingEnabled() && EventXplatEnabled")
        clrallEvents.append(eventName+"();}\n\n")
        #generate FireEtw functions
        fnptype     = []
        fnbody      = []
        fnptype.append("inline ULONG FireEtw")
        fnptype.append(eventName)
        fnptype.append("(\n")
        fnbody.append(lindent)
        fnbody.append("if (!EventEnabled")
        fnbody.append(eventName)
        fnbody.append("()) {return ERROR_SUCCESS;}\n")
        line        = []
        fnptypeline = []

        if templateName:
            for subTemplate in allTemplates[templateName].allAbstractTemplateTypes:
                fnSig = allTemplates[templateName].getFnFrame(subTemplate)

                for params in fnSig.paramlist:
                    fnparam     = fnSig.getParam(params)
                    wintypeName = fnparam.winType
                    typewName   = palDataTypeMapping[wintypeName]
                    winCount    = fnparam.count
                    countw      = palDataTypeMapping[winCount]
                    fnptypeline.append(lindent)
                    fnptypeline.append(typewName)
                    fnptypeline.append(countw)
                    fnptypeline.append(" ")
                    fnptypeline.append(fnparam.name)
                    fnptypeline.append(",\n")

                #fnsignature
                for params in fnSig.paramlist:
                    fnparam     = fnSig.getParam(params)
                    line.append(fnparam.name)
                    line.append(",")

            #remove trailing commas
            if len(line) > 0:
                del line[-1]
            if len(fnptypeline) > 0:
                del fnptypeline[-1]
        
        fnptype.extend(fnptypeline)
        fnptype.append("\n)\n{\n")
        fnbody.append(lindent)
        fnbody.append("return FireEtXplat")
        fnbody.append(eventName)
        fnbody.append("(")
        fnbody.extend(line)
        fnbody.append(");\n")
        fnbody.append("}\n\n")
                        
        clrallEvents.extend(fnptype)
        clrallEvents.extend(fnbody)
       
    return ''.join(clrallEvents)

def generateClrXplatEvents(eventNodes, allTemplates):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventEnabled
        clrallEvents.append("extern \"C\" BOOL EventXplatEnabled")
        clrallEvents.append(eventName)
        clrallEvents.append("();\n")
        #generate FireEtw functions
        fnptype     = []
        fnptypeline = []
        fnptype.append("extern \"C\" ULONG   FireEtXplat")
        fnptype.append(eventName)
        fnptype.append("(\n")

        if templateName:
            for subTemplate in allTemplates[templateName].allAbstractTemplateTypes:
                fnSig = allTemplates[templateName].getFnFrame(subTemplate)

                for params in fnSig.paramlist:
                    fnparam     = fnSig.getParam(params)
                    wintypeName = fnparam.winType
                    typewName   = palDataTypeMapping[wintypeName]
                    winCount    = fnparam.count
                    countw      = palDataTypeMapping[winCount]
                    fnptypeline.append(lindent)
                    fnptypeline.append(typewName)
                    fnptypeline.append(countw)
                    fnptypeline.append(" ")
                    fnptypeline.append(fnparam.name)
                    fnptypeline.append(",\n")

            #remove trailing commas
            if len(fnptypeline) > 0:
                del fnptypeline[-1]
        
        fnptype.extend(fnptypeline)
        fnptype.append("\n);\n")
        clrallEvents.extend(fnptype)
    
    return ''.join(clrallEvents)

#generates the dummy header file which is used by the VM as entry point to the logging Functions
def generateclrEtwDummy(eventNodes,allTemplates):
    clretmEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        fnptype     = []
        #generate FireEtw functions 
        fnptype.append("#define FireEtw")
        fnptype.append(eventName)
        fnptype.append("(");
        line        = []
        if templateName:
            for subTemplate in allTemplates[templateName].allAbstractTemplateTypes:
                fnSig = allTemplates[templateName].getFnFrame(subTemplate)

                for params in fnSig.paramlist:
                    fnparam     = fnSig.getParam(params)
                    line.append(fnparam.name)
                    line.append(", ")
                
            #remove trailing commas
            if len(line) > 0:
                del line[-1]
        
        fnptype.extend(line)
        fnptype.append(") 0\n")
        clretmEvents.extend(fnptype)

    return ''.join(clretmEvents)

def generateClralltestEvents(sClrEtwAllMan):
    tree           = DOM.parse(sClrEtwAllMan)

    clrtestEvents = []
    for providerNode in tree.getElementsByTagName('provider'):
        templateNodes = providerNode.getElementsByTagName('template')
        allTemplates  = parseTemplateNodes(templateNodes)
        eventNodes = providerNode.getElementsByTagName('event')
        for eventNode in eventNodes:
            eventName    = eventNode.getAttribute('symbol')
            templateName = eventNode.getAttribute('template')
            clrtestEvents.append(" EventXplatEnabled" + eventName + "();\n")
            clrtestEvents.append("Error |= FireEtXplat" + eventName + "(\n")


            line =[]
            if templateName :
                for subTemplate in allTemplates[templateName].allAbstractTemplateTypes:
                    fnSig = allTemplates[templateName].getFnFrame(subTemplate)

                    for params in fnSig.paramlist:
                        argline =''
                        fnparam     = fnSig.getParam(params)
                        if fnparam.name.lower() == 'count':
                            argline = '2'
                        else:
                            if fnparam.winType == "win:Binary":
                                argline = 'win_Binary'
                            elif fnparam.winType == "win:Pointer" and fnparam.count == "win:count":
                                argline = "(const void**)&var11"
                            elif fnparam.winType == "win:Pointer" :
                                argline = "(const void*)var11"
                            elif fnparam.winType =="win:AnsiString":
                                argline    = '" Testing AniString "'
                            elif fnparam.winType =="win:UnicodeString":
                                argline    = 'W(" Testing UnicodeString ")'
                            else:
                                if fnparam.count == "win:count":
                                    line.append("&")

                                argline = fnparam.winType.replace(":","_")

                        line.append(argline)
                        line.append(",\n")
                    
                #remove trailing commas
                if len(line) > 0:
                    del line[-1]
                    line.append("\n")
            line.append(");\n")
            clrtestEvents.extend(line)

    return ''.join(clrtestEvents)




def generateSanityTest(sClrEtwAllMan,testDir):
    if not os.path.exists(testDir):
        os.makedirs(testDir)

    cmake_file = testDir + "/CMakeLists.txt"
    test_cpp   = testDir + "/clralltestevents.cpp"
    testinfo   = testDir + "/testinfo.dat"
    Cmake_file = open(cmake_file,'w')
    Test_cpp   = open(test_cpp,'w')
    Testinfo   = open(testinfo,'w')
    
    #CMake File:
    print >>Cmake_file, stdprolog_cmake
    print >>Cmake_file, """
    cmake_minimum_required(VERSION 2.8.12.2)
    set(CMAKE_INCLUDE_CURRENT_DIR ON)
    set(SOURCES
    """
    print >>Cmake_file, test_cpp
    print >>Cmake_file, """
        )
    include_directories($ENV{__GeneratedIntermediatesDir}/inc)
    include_directories(${COREPAL_SOURCE_DIR}/inc/rt)

    add_executable(eventprovidertest
                  ${SOURCES}
                   )
    set(EVENT_PROVIDER_DEPENDENCIES "")
    set(EVENT_PROVIDER_LINKER_OTPTIONS "")
    if(CMAKE_SYSTEM_NAME STREQUAL Linux)
        add_definitions(-DFEATURE_EVENT_TRACE=1)
            list(APPEND EVENT_PROVIDER_DEPENDENCIES
                 coreclrtraceptprovider
                 eventprovider
                 )
            list(APPEND EVENT_PROVIDER_LINKER_OTPTIONS
                 ${EVENT_PROVIDER_DEPENDENCIES}
                 )

    endif(CMAKE_SYSTEM_NAME STREQUAL Linux)

    add_dependencies(eventprovidertest  ${EVENT_PROVIDER_DEPENDENCIES} coreclrpal)
    target_link_libraries(eventprovidertest
                          coreclrpal
                          ${EVENT_PROVIDER_LINKER_OTPTIONS}
                          )
    """
    print >>Testinfo, """
 Copyright (c) Microsoft Corporation.  All rights reserved.
 #

 Version = 1.0
 Section = EventProvider
 Function = EventProvider
 Name = PAL test for FireEtW* and EventEnabled* functions
 TYPE = DEFAULT
 EXE1 = eventprovidertest
 Description
 =This is a sanity test to check that there are no crashes in Xplat eventing
    """

    #Test.cpp
    print >>Test_cpp, stdprolog
    print >>Test_cpp, """
/*=====================================================================
**
** Source:   clralltestevents.cpp
**
** Purpose:  Ensure Correctness of Eventing code
**
**
**===================================================================*/
#include <palsuite.h>
#include <clrxplatevents.h>

typedef struct _Struct1 {
                ULONG   Data1;
                unsigned short Data2;
                unsigned short Data3;
                unsigned char  Data4[8];
} Struct1;

Struct1 var21[2] = { { 245, 13, 14, "deadbea" }, { 542, 0, 14, "deadflu" } };

Struct1* var11 = var21;
Struct1* win_Struct = var21;

GUID win_GUID ={ 245, 13, 14, "deadbea" };
double win_Double =34.04;
ULONG win_ULong = 34;
BOOL win_Boolean = FALSE;
unsigned __int64 win_UInt64 = 114;
unsigned int win_UInt32 = 4;
unsigned short win_UInt16 = 12;
unsigned char win_UInt8 = 9;
int win_Int32 = 12;
BYTE* win_Binary =(BYTE*)var21 ; 
int __cdecl main(int argc, char **argv)
{

            /* Initialize the PAL.
            */

            if(0 != PAL_Initialize(argc, argv))
            {
               return FAIL;
            }

            ULONG Error = ERROR_SUCCESS;
#if defined(FEATURE_EVENT_TRACE)
            Trace("\\n Starting functional  eventing APIs tests  \\n");
"""

    print >>Test_cpp, generateClralltestEvents(sClrEtwAllMan)
    print >>Test_cpp,"""
/* Shutdown the PAL.
 */

         if (Error != ERROR_SUCCESS)
         {
             Fail("One or more eventing Apis failed\\n ");
             return FAIL;
          }
          Trace("\\n All eventing APIs were fired succesfully \\n");
#endif //defined(FEATURE_EVENT_TRACE)
          PAL_Terminate();
          return PASS;
                                 }

"""
    Cmake_file.close()
    Test_cpp.close()
    Testinfo.close()

def generateEtmDummyHeader(sClrEtwAllMan,clretwdummy):
    tree           = DOM.parse(sClrEtwAllMan)

    incDir = os.path.dirname(os.path.realpath(clretwdummy))
    if not os.path.exists(incDir):
        os.makedirs(incDir)
    Clretwdummy    = open(clretwdummy,'w')
    Clretwdummy.write(stdprolog + "\n")

    for providerNode in tree.getElementsByTagName('provider'):
        templateNodes = providerNode.getElementsByTagName('template')
        allTemplates  = parseTemplateNodes(templateNodes)
        eventNodes = providerNode.getElementsByTagName('event')
        #pal: create etmdummy.h
        Clretwdummy.write(generateclrEtwDummy(eventNodes, allTemplates) + "\n")
    
    Clretwdummy.close()

def generatePlformIndependentFiles(sClrEtwAllMan,incDir,etmDummyFile, testDir):
    tree           = DOM.parse(sClrEtwAllMan)
    if not os.path.exists(incDir):
        os.makedirs(incDir)

    generateSanityTest(sClrEtwAllMan,testDir)
    generateEtmDummyHeader(sClrEtwAllMan,etmDummyFile)
    clrallevents   = incDir + "/clretwallmain.h"
    clrxplatevents = incDir + "/clrxplatevents.h"

    Clrallevents   = open(clrallevents,'w')
    Clrxplatevents = open(clrxplatevents,'w')

    Clrallevents.write(stdprolog + "\n")
    Clrxplatevents.write(stdprolog + "\n")

    Clrallevents.write("\n#include \"clrxplatevents.h\"\n\n")

    for providerNode in tree.getElementsByTagName('provider'):
        templateNodes = providerNode.getElementsByTagName('template')
        allTemplates  = parseTemplateNodes(templateNodes)
        eventNodes = providerNode.getElementsByTagName('event')
        #vm header: 
        Clrallevents.write(generateClrallEvents(eventNodes, allTemplates) + "\n")

        #pal: create clrallevents.h
        Clrxplatevents.write(generateClrXplatEvents(eventNodes, allTemplates) + "\n")


    Clrxplatevents.close()
    Clrallevents.close()

class EventExclusions:
    def __init__(self):
        self.nostack         = set()
        self.explicitstack   = set()
        self.noclrinstance   = set()

def parseExclusionList(exclusionListFile):
    ExclusionFile   = open(exclusionListFile,'r')
    exclusionInfo   = EventExclusions()

    for line in ExclusionFile:
        line = line.strip()
        
        #remove comments
        if not line or line.startswith('#'):
            continue

        tokens = line.split(':')
        #entries starting with nomac are ignored
        if "nomac" in tokens:
            continue

        if len(tokens) > 5:
            raise Exception("Invalid Entry " + line + "in "+ exclusionListFile)

        eventProvider = tokens[2]
        eventTask     = tokens[1]
        eventSymbol   = tokens[4]

        if eventProvider == '':
            eventProvider = "*"
        if eventTask     == '':
            eventTask     = "*"
        if eventSymbol   == '':
            eventSymbol   = "*"
        entry = eventProvider + ":" + eventTask + ":" + eventSymbol

        if tokens[0].lower() == "nostack":
            exclusionInfo.nostack.add(entry)
        if tokens[0].lower() == "stack":
            exclusionInfo.explicitstack.add(entry)
        if tokens[0].lower() == "noclrinstanceid":
            exclusionInfo.noclrinstance.add(entry)
    ExclusionFile.close()

    return exclusionInfo

def getStackWalkBit(eventProvider, taskName, eventSymbol, stackSet):
    for entry in stackSet:
        tokens = entry.split(':')

        if len(tokens) != 3:
            raise Exception("Error, possible error in the script which introduced the enrty "+ entry)
        
        eventCond  = tokens[0] == eventProvider or tokens[0] == "*"
        taskCond   = tokens[1] == taskName      or tokens[1] == "*"
        symbolCond = tokens[2] == eventSymbol   or tokens[2] == "*"

        if eventCond and taskCond and symbolCond:
            return False
    return True

#Add the miscelaneous checks here
def checkConsistency(sClrEtwAllMan,exclusionListFile):
    tree                      = DOM.parse(sClrEtwAllMan)
    exclusionInfo = parseExclusionList(exclusionListFile)
    for providerNode in tree.getElementsByTagName('provider'):

        stackSupportSpecified = {}
        eventNodes            = providerNode.getElementsByTagName('event')
        templateNodes         = providerNode.getElementsByTagName('template')
        eventProvider         = providerNode.getAttribute('name')
        allTemplates          = parseTemplateNodes(templateNodes)

        for eventNode in eventNodes:
            taskName         = eventNode.getAttribute('task')
            eventSymbol      = eventNode.getAttribute('symbol')
            eventTemplate    = eventNode.getAttribute('template')
            eventValue       = int(eventNode.getAttribute('value'))
            clrInstanceBit   = getStackWalkBit(eventProvider, taskName, eventSymbol, exclusionInfo.noclrinstance)
            sLookupFieldName = "ClrInstanceID"
            sLookupFieldType = "win:UInt16"

            if clrInstanceBit and allTemplates.get(eventTemplate):
                # check for the event template and look for a field named ClrInstanceId of type win:UInt16
                fnParam = allTemplates[eventTemplate].getFnParam(sLookupFieldName)

                if not(fnParam and fnParam.winType == sLookupFieldType):
                    raise Exception(exclusionListFile + ":No " + sLookupFieldName + " field of type " + sLookupFieldType + " for event symbol " +  eventSymbol)

            
            # If some versions of an event are on the nostack/stack lists,
            # and some versions are not on either the nostack or stack list,
            # then developer likely forgot to specify one of the versions

            eventStackBitFromNoStackList       = getStackWalkBit(eventProvider, taskName, eventSymbol, exclusionInfo.nostack)
            eventStackBitFromExplicitStackList = getStackWalkBit(eventProvider, taskName, eventSymbol, exclusionInfo.explicitstack)
            sStackSpecificityError = exclusionListFile + ": Error processing event :" + eventSymbol + "(ID" + str(eventValue) + "): This file must contain either ALL versions of this event or NO versions of this event. Currently some, but not all, versions of this event are present\n"

            if not stackSupportSpecified.get(eventValue):
                 # Haven't checked this event before.  Remember whether a preference is stated
                if ( not eventStackBitFromNoStackList) or ( not eventStackBitFromExplicitStackList):
                    stackSupportSpecified[eventValue] = True
                else:
                    stackSupportSpecified[eventValue] = False 
            else:
                # We've checked this event before.
                if stackSupportSpecified[eventValue]:
                    # When we last checked, a preference was previously specified, so it better be specified here
                    if eventStackBitFromNoStackList and eventStackBitFromExplicitStackList:
                        raise Exception(sStackSpecificityError)
                else:
                    # When we last checked, a preference was not previously specified, so it better not be specified here
                    if ( not eventStackBitFromNoStackList) or ( not eventStackBitFromExplicitStackList):
                        raise Exception(sStackSpecificityError)
import argparse
import sys

def main(argv):

    #parse the command line
    parser = argparse.ArgumentParser(description="Generates the Code required to instrument LTTtng logging mechanism")

    required = parser.add_argument_group('required arguments')
    required.add_argument('--man',  type=str, required=True,
                                    help='full path to manifest containig the description of events')
    required.add_argument('--exc',  type=str, required=True,
                                    help='full path to exclusion list')
    required.add_argument('--inc',  type=str, required=True,
                                    help='full path to directory where the header files will be generated')
    required.add_argument('--dummy',  type=str, required=True,
                                    help='full path to file that will have dummy definitions of FireEtw functions')
    required.add_argument('--testdir',  type=str, required=True,
                                    help='full path to directory where the test assets will be deployed' )
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print('Unknown argument(s): ', ', '.join(unknown))
        return const.UnknownArguments

    sClrEtwAllMan     = args.man
    exclusionListFile = args.exc
    incdir            = args.inc
    etmDummyFile      = args.dummy
    testDir           = args.testdir

    checkConsistency(sClrEtwAllMan, exclusionListFile)
    generatePlformIndependentFiles(sClrEtwAllMan,incdir,etmDummyFile,testDir)

if __name__ == '__main__':
    return_code = main(sys.argv[1:])
    sys.exit(return_code)


