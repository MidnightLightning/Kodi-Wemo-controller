#!/usr/bin/env python
################################
# Interactive UPNP application #
# Craig Heffner                #
# www.sourcesec.com            #
# 07/16/2008                   #
#
# Notes from Issac:
# http://code.google.com/p/miranda-upnp/
# Marks this file as GPL3 licensed by the author
# I have made minor modificatinos to get it to work with the wemo
#
################################

try:
    import sys,os
    from socket import *
    from urllib2 import URLError, HTTPError
    import xml.dom.minidom as minidom
    import IN,urllib2
    import time
    import struct
    import re
except Exception,e:
    print 'Unmet dependency:',e
    sys.exit(1)

try:
    import xbmc
except Exception,e:
    class Xbmc:
        """ A mock XBMC module """
        abortRequested = False
        def log(self, msg):
            print msg
    xbmc = Xbmc()


#Most of the cmdCompleter class was originally written by John Kenyan
#It serves to tab-complete commands inside the program's shell
class cmdCompleter:
    def __init__(self,commands):
        self.commands = commands

    #Traverses the list of available commands
    def traverse(self,tokens,tree):
        retVal = []

        #If there are no commands, or no user input, return null
        if tree is None or len(tokens) == 0:
            return []
        #If there is only one word, only auto-complete the primary commands
        elif len(tokens) == 1:
            retVal = [x+' ' for x in tree if x.startswith(tokens[0])]
        #Else auto-complete for the sub-commands
        elif tokens[0] in tree.keys():
            retVal = self.traverse(tokens[1:],tree[tokens[0]])
        return retVal

#UPNP class for getting, sending and parsing SSDP/SOAP XML data (among other things...)
class upnp:
    ip = False
    port = False
    completer = False
    msearchHeaders = {
        'MAN' : '"ssdp:discover"',
        'MX'  : '2'
    }
    DEFAULT_IP = "239.255.255.250"
    DEFAULT_PORT = 1900
    UPNP_VERSION = '1.0'
    MAX_RECV = 8192
    HTTP_HEADERS = []
    ENUM_HOSTS = {}
    VERBOSE = False
    UNIQ = False
    DEBUG = False
    LOG_FILE = False
    IFACE = None
    STARS = '****************************************************************'
    csock = False
    ssock = False

    def __init__(self, ip=False, port=False, iface=None, appCommands=[]):
        if appCommands:
            self.completer = cmdCompleter(appCommands)
        if self.initSockets(ip, port, iface) == False:
            xbmc.log('Miranda: UPNP class initialization failed!')
            sys.exit(1)
        else:
            self.soapEnd = re.compile('<\/.*:envelope>')
            xbmc.log('Miranda: UPNP class initialized')

    # Initialize default sockets
    def initSockets(self, ip, port, iface):
        if self.csock:
            self.csock.close()
        if self.ssock:
            self.ssock.close()

        if iface != None:
            self.IFACE = iface
        if not ip:
            ip = self.DEFAULT_IP
            if not port:
                port = self.DEFAULT_PORT
            self.port = port
            self.ip = ip

        try:
            # This is needed to join a multicast group
            self.mreq = struct.pack("4sl",inet_aton(ip),INADDR_ANY)

            # Set up client socket
            self.csock = socket(AF_INET,SOCK_DGRAM)
            self.csock.setsockopt(IPPROTO_IP,IP_MULTICAST_TTL,2)

            # Set up server socket
            self.ssock = socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP)
            self.ssock.setsockopt(SOL_SOCKET,SO_REUSEADDR,1)

            # Only bind to this interface
            if self.IFACE != None:
                print '\nBinding to interface',self.IFACE,'...\n'
                self.ssock.setsockopt(SOL_SOCKET,IN.SO_BINDTODEVICE,struct.pack("%ds" % (len(self.IFACE)+1,), self.IFACE))
                self.csock.setsockopt(SOL_SOCKET,IN.SO_BINDTODEVICE,struct.pack("%ds" % (len(self.IFACE)+1,), self.IFACE))

            try:
                self.ssock.bind(('',self.port))
            except Exception, e:
                print "WARNING: Failed to bind %s:%d: %s" , (self.ip,self.port,e)
            try:
                self.ssock.setsockopt(IPPROTO_IP,IP_ADD_MEMBERSHIP,self.mreq)
            except Exception, e:
                print 'WARNING: Failed to join multicast group:',e
        except Exception, e:
            print "Failed to initialize UPNP sockets:",e
            return False
        return True

    # Clean up file/socket descriptors
    def cleanup(self):
        if self.LOG_FILE != False:
            self.LOG_FILE.close()
        self.csock.close()
        self.ssock.close()

    # Send network data
    def send(self,data,socket):
        # By default, use the client socket that's part of this class
        if socket == False:
            socket = self.csock
        try:
            socket.sendto(data,(self.ip,self.port))
            return True
        except Exception, e:
            xbmc.log('Miranda: SendTo method failed for %s:%d : %s' % (self.ip,self.port,e))
            return False

    #Listen for network data
    def listen(self,size,socket):
        if socket == False:
            socket = self.ssock

        sock.settimeout(10)
        try:
            return socket.recv(size)
        except Exception,e:
            xbmc.log('Miranda: Listen exception: %s' % e)
            return False

    #Create new UDP socket on ip, bound to port
    def createNewListener(self,ip=gethostbyname(gethostname()),port=1900):
        try:
            newsock = socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP)
            newsock.setsockopt(SOL_SOCKET,SO_REUSEADDR,1)
            newsock.bind((ip,port))
            return newsock
        except Exception,e:
            xbmc.log('Miranda: Listener exception: %s' % e)
            return False

    #Return the class's primary server socket
    def listener(self):
        return self.ssock

    #Return the class's primary client socket
    def sender(self):
        return self.csock

    #Parse a URL, return the host and the page
    def parseURL(self,url):
        delim = '://'
        host = False
        page = False

        #Split the host and page
        try:
            (host,page) = url.split(delim)[1].split('/',1)
            page = '/' + page
        except:
            #If '://' is not in the url, then it's not a full URL, so assume that it's just a relative path
            page = url

        return (host,page)

    #Pull the name of the device type from a device type string
    #The device type string looks like: 'urn:schemas-upnp-org:device:WANDevice:1'
    def parseDeviceTypeName(self,string):
        delim1 = 'device:'
        delim2 = ':'

        if delim1 in string and not string.endswith(delim1):
            return string.split(delim1)[1].split(delim2,1)[0]
        return False

    #Pull the name of the service type from a service type string
    #The service type string looks like: 'urn:schemas-upnp-org:service:Layer3Forwarding:1'
    def parseServiceTypeName(self,string):
        delim1 = 'service:'
        delim2 = ':'

        if delim1 in string and not string.endswith(delim1):
            return string.split(delim1)[1].split(delim2,1)[0]
        return False

    #Pull the header info for the specified HTTP header - case insensitive
    def parseHeader(self,data,header):
        delimiter = "%s:" % header
        defaultRet = False

        lowerDelim = delimiter.lower()
        dataArray = data.split("\r\n")

        #Loop through each line of the headers
        for line in dataArray:
            lowerLine = line.lower()
            #Does this line start with the header we're looking for?
            if lowerLine.startswith(lowerDelim):
                try:
                    return line.split(':',1)[1].strip()
                except:
                    print "Failure parsing header data for %s" % header
        return defaultRet

    #Extract the contents of a single XML tag from the data
    def extractSingleTag(self,data,tag):
        startTag = "<%s" % tag
        endTag = "</%s>" % tag

        try:
            tmp = data.split(startTag)[1]
            index = tmp.find('>')
            if index != -1:
                index += 1
                return tmp[index:].split(endTag)[0].strip()
        except:
            pass
        return None

    #Parses SSDP notify and reply packets, and populates the ENUM_HOSTS dict
    def parseSSDPInfo(self,data,showUniq,verbose):
        hostFound = False
        messageType = False
        xmlFile = False
        host = False
        page = False
        upnpType = None
        knownHeaders = {
            'NOTIFY' : 'notification',
            'HTTP/1.1 200 OK' : 'reply'
        }

        #Use the class defaults if these aren't specified
        if showUniq == False:
            showUniq = self.UNIQ
        if verbose == False:
            verbose = self.VERBOSE

        #Is the SSDP packet a notification, a reply, or neither?
        for text,messageType in knownHeaders.iteritems():
            if data.upper().startswith(text):
                break
            else:
                messageType = False

        #If this is a notification or a reply message...
        if messageType != False:
            #Get the host name and location of it's main UPNP XML file
            xmlFile = self.parseHeader(data,"LOCATION")
            upnpType = self.parseHeader(data,"SERVER")
            (host,page) = self.parseURL(xmlFile)

            #Sanity check to make sure we got all the info we need
            if xmlFile == False or host == False or page == False:
                print 'ERROR parsing recieved header:'
                print self.STARS
                print data
                print self.STARS
                print ''
                return False

            #Get the protocol in use (i.e., http, https, etc)
            protocol = xmlFile.split('://')[0]+'://'

            #Check if we've seen this host before; add to the list of hosts if:
            #    1. This is a new host
            #    2. We've already seen this host, but the uniq hosts setting is disabled
            for hostID,hostInfo in self.ENUM_HOSTS.iteritems():
                if hostInfo['name'] == host:
                    hostFound = True
                    if self.UNIQ:
                        return False

            if (hostFound and not self.UNIQ) or not hostFound:
                #Get the new host's index number and create an entry in ENUM_HOSTS
                index = len(self.ENUM_HOSTS)
                self.ENUM_HOSTS[index] = {
                    'name' : host,
                    'dataComplete' : False,
                    'proto' : protocol,
                    'xmlFile' : xmlFile,
                    'serverType' : None,
                    'upnpServer' : upnpType,
                    'deviceList' : {}
                }
                #Be sure to update the command completer so we can tab complete through this host's data structure
                self.updateCmdCompleter(self.ENUM_HOSTS)

            #Print out some basic device info
            print self.STARS
            print "SSDP %s message from %s" % (messageType,host)

            if xmlFile:
                print "XML file is located at %s" % xmlFile

            if upnpType:
                print "Device is running %s"% upnpType

            print self.STARS
            print ''

    #Send GET request for a UPNP XML file
    def getXML(self, url):

        headers = {
            'USER-AGENT':'uPNP/'+self.UPNP_VERSION,
            'CONTENT-TYPE':'text/xml; charset="utf-8"'
        }

        try:
            #Use urllib2 for the request, it's awesome
            req = urllib2.Request(url, None, headers)
            response = urllib2.urlopen(req)
            output = response.read()
            headers = response.info()
            return (headers,output)
        except Exception, e:
            print "Request for '%s' failed: %s" % (url,e)
            return (False,False)

    #Send SOAP request
    def sendSOAP(self, hostName, serviceType, controlURL, actionName, actionArguments):
        argList = ''
        soapResponse = ''

        if '://' in controlURL:
            urlArray = controlURL.split('/',3)
            if len(urlArray) < 4:
                controlURL = '/'
            else:
                controlURL = '/' + urlArray[3]


        soapRequest = 'POST %s HTTP/1.1\r\n' % controlURL

        #Check if a port number was specified in the host name; default is port 80
        if ':' in hostName:
            hostNameArray = hostName.split(':')
            host = hostNameArray[0]
            try:
                port = int(hostNameArray[1])
            except:
                xbmc.log('Miranda: Invalid port specified for host connection:',hostName[1])
                return False
        else:
            host = hostName
            port = 80

        #Create a string containing all of the SOAP action's arguments and values
        for arg,(val,dt) in actionArguments.iteritems():
            argList += '<%s>%s</%s>' % (arg,val,arg)

        #Create the SOAP request
        soapBody =     """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
 <s:Body>
  <u:%s xmlns:u="%s">
   %s
  </u:%s>
 </s:Body>
</s:Envelope>
""" % (actionName, serviceType, argList, actionName)

        #Specify the headers to send with the request
        headers =     {
            'Content-Type':'text/xml; charset="utf-8"',
            'SOAPACTION':'"%s#%s"' % (serviceType,actionName),
            'Content-Length': len(soapBody),
            'HOST':hostName,
            'User-Agent': 'CyberGarage-HTTP/1.0',
        }

        #Generate the final payload
        for head,value in headers.iteritems():
            soapRequest += '%s: %s\r\n' % (head,value)
        soapRequest += '\r\n%s' % soapBody

        #Send data and go into recieve loop
        try:
            sock = socket(AF_INET,SOCK_STREAM)
            sock.connect((host,port))
            sock.send(soapRequest)
            while True:
                data = sock.recv(self.MAX_RECV)
                if not data:
                    break
                else:
                    soapResponse += data
                    if self.soapEnd.search(soapResponse.lower()) != None:
                        break
            sock.close()

            (header,body) = soapResponse.split('\r\n\r\n',1)
            if not header.upper().startswith('HTTP/1.1 200'):
                print 'SOAP request failed with error code:',header.split('\r\n')[0].split(' ',1)[1]
                errorMsg = self.extractSingleTag(body,'errorDescription')
                if errorMsg:
                    xbmc.log('Miranda: SOAP error message:',errorMsg)
                return False
            else:
                return body
        except Exception, e:
            xbmc.log('Miranda: Caught socket exception:',e)
            sock.close()
            return False
        except KeyboardInterrupt:
            sock.close()
        return False

    #Display all info for a given host
    def showCompleteHostInfo(self,index,fp):
        serviceKeys = ['controlURL','eventSubURL','serviceId','SCPDURL','fullName']
        if fp == False:
            fp = sys.stdout

        if index < 0 or index >= len(self.ENUM_HOSTS):
            fp.write('Specified host does not exist...\n')
            return
        try:
            hostInfo = self.ENUM_HOSTS[index]
            if hostInfo['dataComplete'] == False:
                print "Cannot show all host info because we don't have it all yet. Try running 'host info %d' first...\n" % index
            fp.write('Host name:         %s\n' % hostInfo['name'])
            fp.write('UPNP XML File:     %s\n\n' % hostInfo['xmlFile'])

            fp.write('\nDevice information:\n')
            for deviceName,deviceStruct in hostInfo['deviceList'].iteritems():
                fp.write('\tDevice Name: %s\n' % deviceName)
                for serviceName,serviceStruct in deviceStruct['services'].iteritems():
                    fp.write('\t\tService Name: %s\n' % serviceName)
                    for key in serviceKeys:
                        fp.write('\t\t\t%s: %s\n' % (key,serviceStruct[key]))
                    fp.write('\t\t\tServiceActions:\n')
                    for actionName,actionStruct in serviceStruct['actions'].iteritems():
                        fp.write('\t\t\t\t%s\n' % actionName)
                        for argName,argStruct in actionStruct['arguments'].iteritems():
                            fp.write('\t\t\t\t\t%s \n' % argName)
                            for key,val in argStruct.iteritems():
                                try:
                                    if key == 'relatedStateVariable':
                                        fp.write('\t\t\t\t\t\t%s:\n' % val)
                                        for k,v in serviceStruct['serviceStateVariables'][val].iteritems():
                                            fp.write('\t\t\t\t\t\t\t%s: %s\n' % (k,v))
                                    else:
                                        fp.write('\t\t\t\t\t\t%s: %s\n' % (key,val))
                                except:
                                    pass

        except Exception, e:
            print 'Caught exception while showing host info:',e

    #Wrapper function...
    def getHostInfo(self, xmlData, xmlHeaders, index):
        if self.ENUM_HOSTS[index]['dataComplete'] == True:
            return

        if index >= 0 and index < len(self.ENUM_HOSTS):
            try:
                xmlRoot = minidom.parseString(xmlData)
                self.parseDeviceInfo(xmlRoot,index)
                self.ENUM_HOSTS[index]['serverType'] = xmlHeaders.getheader('Server')
                self.ENUM_HOSTS[index]['dataComplete'] = True
                return True
            except Exception, e:
                xbmc.log('Miranda: Caught exception while getting host info: %s' % e)
        return False

    #Parse device info from the retrieved XML file
    def parseDeviceInfo(self,xmlRoot,index):
        deviceEntryPointer = False
        devTag = "device"
        deviceType = "deviceType"
        deviceListEntries = "deviceList"
        deviceTags = ["friendlyName","modelDescription","modelName","modelNumber","modelURL","presentationURL","UDN","UPC","manufacturer","manufacturerURL"]

        #Find all device entries listed in the XML file
        for device in xmlRoot.getElementsByTagName(devTag):
            try:
                #Get the deviceType string
                deviceTypeName = str(device.getElementsByTagName(deviceType)[0].childNodes[0].data)
            except:
                continue

            #Pull out the action device name from the deviceType string
            deviceDisplayName = self.parseDeviceTypeName(deviceTypeName)
            if not deviceDisplayName:
                continue

            #Create a new device entry for this host in the ENUM_HOSTS structure
            deviceEntryPointer = self.ENUM_HOSTS[index][deviceListEntries][deviceDisplayName] = {}
            deviceEntryPointer['fullName'] = deviceTypeName

            #Parse out all the device tags for that device
            for tag in deviceTags:
                try:
                    deviceEntryPointer[tag] = str(device.getElementsByTagName(tag)[0].childNodes[0].data)
                except Exception:
                    if self.VERBOSE:
                        print 'Device',deviceEntryPointer['fullName'],'does not have a',tag
                    continue
            #Get a list of all services for this device listing
            self.parseServiceList(device,deviceEntryPointer,index)

    #Parse the list of services specified in the XML file
    def parseServiceList(self,xmlRoot,device,index):
        serviceEntryPointer = False
        dictName = "services"
        serviceListTag = "serviceList"
        serviceTag = "service"
        serviceNameTag = "serviceType"
        serviceTags = ["serviceId","controlURL","eventSubURL","SCPDURL"]

        try:
            device[dictName] = {}
            #Get a list of all services offered by this device
            for service in xmlRoot.getElementsByTagName(serviceListTag)[0].getElementsByTagName(serviceTag):
                #Get the full service descriptor
                serviceName = str(service.getElementsByTagName(serviceNameTag)[0].childNodes[0].data)

                #Get the service name from the service descriptor string
                serviceDisplayName = self.parseServiceTypeName(serviceName)
                if not serviceDisplayName:
                    continue

                #Create new service entry for the device in ENUM_HOSTS
                serviceEntryPointer = device[dictName][serviceDisplayName] = {}
                serviceEntryPointer['fullName'] = serviceName

                #Get all of the required service info and add it to ENUM_HOSTS
                for tag in serviceTags:
                    serviceEntryPointer[tag] = str(service.getElementsByTagName(tag)[0].childNodes[0].data)

                #Get specific service info about this service
                self.parseServiceInfo(serviceEntryPointer,index)
        except Exception, e:
            print 'Caught exception while parsing device service list:',e

    #Parse details about each service (arguements, variables, etc)
    def parseServiceInfo(self,service,index):
        argIndex = 0
        argTags = ['direction','relatedStateVariable']
        actionList = 'actionList'
        actionTag = 'action'
        nameTag = 'name'
        argumentList = 'argumentList'
        argumentTag = 'argument'

        #Get the full path to the service's XML file
        xmlFile = self.ENUM_HOSTS[index]['proto'] + self.ENUM_HOSTS[index]['name']
        if not xmlFile.endswith('/') and not service['SCPDURL'].startswith('/'):
            xmlFile += '/'
        if self.ENUM_HOSTS[index]['proto'] in service['SCPDURL']:
            xmlFile = service['SCPDURL']
        else:
            xmlFile += service['SCPDURL']
        service['actions'] = {}

        #Get the XML file that describes this service
        (xmlHeaders,xmlData) = self.getXML(xmlFile)
        if not xmlData:
            print 'Failed to retrieve service descriptor located at:',xmlFile
            return False

        try:
            xmlRoot = minidom.parseString(xmlData)

            #Get a list of actions for this service
            try:
                actionList = xmlRoot.getElementsByTagName(actionList)[0]
            except:
                print 'Failed to retrieve action list for service %s!' % service['fullName']
                return False
            actions = actionList.getElementsByTagName(actionTag)
            if actions == []:
                print 'Failed to retrieve actions from service actions list for service %s!' % service['fullName']
                return False

            #Parse all actions in the service's action list
            for action in actions:
                #Get the action's name
                try:
                    actionName = str(action.getElementsByTagName(nameTag)[0].childNodes[0].data).strip()
                except:
                    print 'Failed to obtain service action name (%s)!' % service['fullName']
                    continue

                #Add the action to the ENUM_HOSTS dictonary
                service['actions'][actionName] = {}
                service['actions'][actionName]['arguments'] = {}

                #Parse all of the action's arguments
                try:
                    argList = action.getElementsByTagName(argumentList)[0]
                except:
                    #Some actions may take no arguments, so continue without raising an error here...
                    continue

                #Get all the arguments in this action's argument list
                arguments = argList.getElementsByTagName(argumentTag)
                if arguments == []:
                    if self.VERBOSE:
                        print 'Action',actionName,'has no arguments!'
                    continue

                #Loop through the action's arguments, appending them to the ENUM_HOSTS dictionary
                for argument in arguments:
                    try:
                        argName = str(argument.getElementsByTagName(nameTag)[0].childNodes[0].data)
                    except:
                        print 'Failed to get argument name for',actionName
                        continue
                    service['actions'][actionName]['arguments'][argName] = {}

                    #Get each required argument tag value and add them to ENUM_HOSTS
                    for tag in argTags:
                        try:
                            service['actions'][actionName]['arguments'][argName][tag] = str(argument.getElementsByTagName(tag)[0].childNodes[0].data)
                        except:
                            print 'Failed to find tag %s for argument %s!' % (tag,argName)
                            continue

            #Parse all of the state variables for this service
            self.parseServiceStateVars(xmlRoot,service)

        except Exception, e:
            print 'Caught exception while parsing Service info for service %s: %s' % (service['fullName'],str(e))
            return False

        return True

    #Get info about a service's state variables
    def parseServiceStateVars(self,xmlRoot,servicePointer):

        na = 'N/A'
        varVals = ['sendEvents','dataType','defaultValue','allowedValues']
        serviceStateTable = 'serviceStateTable'
        stateVariable = 'stateVariable'
        nameTag = 'name'
        dataType = 'dataType'
        sendEvents = 'sendEvents'
        allowedValueList = 'allowedValueList'
        allowedValue = 'allowedValue'
        allowedValueRange = 'allowedValueRange'
        minimum = 'minimum'
        maximum = 'maximum'

        #Create the serviceStateVariables entry for this service in ENUM_HOSTS
        servicePointer['serviceStateVariables'] = {}

        #Get a list of all state variables associated with this service
        try:
            stateVars = xmlRoot.getElementsByTagName(serviceStateTable)[0].getElementsByTagName(stateVariable)
        except:
            #Don't necessarily want to throw an error here, as there may be no service state variables
            return False

        #Loop through all state variables
        for var in stateVars:
            for tag in varVals:
                #Get variable name
                try:
                    varName = str(var.getElementsByTagName(nameTag)[0].childNodes[0].data)
                except:
                    print 'Failed to get service state variable name for service %s!' % servicePointer['fullName']
                    continue

                servicePointer['serviceStateVariables'][varName] = {}
                try:
                    servicePointer['serviceStateVariables'][varName]['dataType'] = str(var.getElementsByTagName(dataType)[0].childNodes[0].data)
                except:
                    servicePointer['serviceStateVariables'][varName]['dataType'] = na
                try:
                    servicePointer['serviceStateVariables'][varName]['sendEvents'] = str(var.getElementsByTagName(sendEvents)[0].childNodes[0].data)
                except:
                    servicePointer['serviceStateVariables'][varName]['sendEvents'] = na

                servicePointer['serviceStateVariables'][varName][allowedValueList] = []

                #Get a list of allowed values for this variable
                try:
                    vals = var.getElementsByTagName(allowedValueList)[0].getElementsByTagName(allowedValue)
                except:
                    pass
                else:
                    #Add the list of allowed values to the ENUM_HOSTS dictionary
                    for val in vals:
                        servicePointer['serviceStateVariables'][varName][allowedValueList].append(str(val.childNodes[0].data))

                #Get allowed value range for this variable
                try:
                    valList = var.getElementsByTagName(allowedValueRange)[0]
                except:
                    pass
                else:
                    #Add the max and min values to the ENUM_HOSTS dictionary
                    servicePointer['serviceStateVariables'][varName][allowedValueRange] = []
                    try:
                        servicePointer['serviceStateVariables'][varName][allowedValueRange].append(str(valList.getElementsByTagName(minimum)[0].childNodes[0].data))
                        servicePointer['serviceStateVariables'][varName][allowedValueRange].append(str(valList.getElementsByTagName(maximum)[0].childNodes[0].data))
                    except:
                        pass
        return True

    #Update the command completer
    def updateCmdCompleter(self,struct):
        indexOnlyList = {
                'host' : ['get','details','summary'],
                'save' : ['info']
        }
        hostCommand = 'host'
        subCommandList = ['info']
        sendCommand = 'send'

        try:
            structPtr = {}
            topLevelKeys = {}
            for key,val in struct.iteritems():
                structPtr[str(key)] = val
                topLevelKeys[str(key)] = None

            #Update the subCommandList
            for subcmd in subCommandList:
                self.completer.commands[hostCommand][subcmd] = None
                self.completer.commands[hostCommand][subcmd] = structPtr

            #Update the indexOnlyList
            for cmd,data in indexOnlyList.iteritems():
                for subcmd in data:
                    self.completer.commands[cmd][subcmd] = topLevelKeys

            #This is for updating the sendCommand key
            structPtr = {}
            for hostIndex,hostData in struct.iteritems():
                host = str(hostIndex)
                structPtr[host] = {}
                if hostData.has_key('deviceList'):
                    for device,deviceData in hostData['deviceList'].iteritems():
                        structPtr[host][device] = {}
                        if deviceData.has_key('services'):
                            for service,serviceData in deviceData['services'].iteritems():
                                structPtr[host][device][service] = {}
                                if serviceData.has_key('actions'):
                                    for action,actionData in serviceData['actions'].iteritems():
                                        structPtr[host][device][service][action] = None
            self.completer.commands[hostCommand][sendCommand] = structPtr
        except Exception:
            xbmc.log("Miranda: Error updating command completer structure; some command completion features might not work...")
        return




################## Action Functions ######################
#These functions handle user commands from the shell

#Actively search for UPNP devices
def msearch(argc, argv, hp, cycles=99999999):
    defaultST = "upnp:rootdevice"
    st = "schemas-upnp-org"
    myip = gethostbyname(gethostname())
    lport = hp.port

    if argc >= 3:
        if argc == 4:
            st = argv[1]
            searchType = argv[2]
            searchName = argv[3]
        else:
            searchType = argv[1]
            searchName = argv[2]
        st = "urn:%s:%s:%s:%s" % (st,searchType,searchName,hp.UPNP_VERSION.split('.')[0])
    else:
        st = defaultST

    #Build the request
    request =     "M-SEARCH * HTTP/1.1\r\n"\
            "HOST:%s:%d\r\n"\
            "ST:%s\r\n" % (hp.ip,hp.port,st)
    for header,value in hp.msearchHeaders.iteritems():
            request += header + ':' + value + "\r\n"
    request += "\r\n"

    xbmc.log("Miranda: Entering discovery mode for '%s', Ctl+C to stop..." % st)

    #Have to create a new socket since replies will be sent directly to our IP, not the multicast IP
    server = hp.createNewListener(myip,lport)
    if server == False:
        xbmc.log('Miranda: Failed to bind port %d' % lport)
        return
    hp.send(request,server)
    while True:
        xbmc.log('Miranda: Parsing server data...')
        try:
            hp.parseSSDPInfo(hp.listen(1024,server),False,False)
        except Exception, e:
            xbmc.log('Miranda: Discover mode halted due to exception: %s' % e)
            server.close()
            break
        cycles -= 1
        if (cycles == 0 or xbmc.abortRequested):
            xbmc.log('Miranda: Discover mode halted...')
            server.close()
            break

#Passively listen for UPNP NOTIFY packets
def pcap(argc,argv,hp):
    print 'Entering passive mode, Ctl+C to stop...'
    print ''
    while True:
        try:
            hp.parseSSDPInfo(hp.listen(1024,False),False,False)
        except Exception:
            print "Passive mode halted..."
            break

#Manipulate M-SEARCH header values
def head(argc,argv,hp):
    if argc >= 2:
        action = argv[1]
        #Show current headers
        if action == 'show':
            for header,value in hp.msearchHeaders.iteritems():
                print header,':',value
            return
        #Delete the specified header
        elif action == 'del':
            if argc == 3:
                header = argv[2]
                if hp.msearchHeaders.has_key(header):
                    del hp.msearchHeaders[header]
                    print '%s removed from header list' % header
                    return
                else:
                    print '%s is not in the current header list' % header
                    return
        #Create/set a headers
        elif action == 'set':
            if argc == 4:
                header = argv[2]
                value = argv[3]
                hp.msearchHeaders[header] = value
                print "Added header: '%s:%s" % (header,value)
                return

    showHelp(argv[0])

#Manipulate application settings
def seti(argc,argv,hp):
    if argc >= 2:
        action = argv[1]
        if action == 'uniq':
            hp.UNIQ = toggleVal(hp.UNIQ)
            print "Show unique hosts set to: %s" % hp.UNIQ
            return
        elif action == 'debug':
            hp.DEBUG = toggleVal(hp.DEBUG)
            print "Debug mode set to: %s" % hp.DEBUG
            return
        elif action == 'verbose':
            hp.VERBOSE = toggleVal(hp.VERBOSE)
            print "Verbose mode set to: %s" % hp.VERBOSE
            return
        elif action == 'version':
            if argc == 3:
                hp.UPNP_VERSION = argv[2]
                print 'UPNP version set to: %s' % hp.UPNP_VERSION
            else:
                showHelp(argv[0])
            return
        elif action == 'iface':
            if argc == 3:
                hp.IFACE = argv[2]
                print 'Interface set to %s, re-binding sockets...' % hp.IFACE
                if hp.initSockets(hp.ip,hp.port,hp.IFACE):
                    print 'Interface change successful!'
                else:
                    print 'Failed to bind new interface - are you sure you have root privilages??'
                    hp.IFACE = None
                return
        elif action == 'socket':
            if argc == 3:
                try:
                    (ip,port) = argv[2].split(':')
                    port = int(port)
                    hp.ip = ip
                    hp.port = port
                    hp.cleanup()
                    if hp.initSockets(ip,port,hp.IFACE) == False:
                        print "Setting new socket %s:%d failed!" % (ip,port)
                    else:
                        print "Using new socket: %s:%d" % (ip,port)
                except Exception, e:
                    print 'Caught exception setting new socket:',e
                return
        elif action == 'show':
            print 'Multicast IP:          ',hp.ip
            print 'Multicast Port:        ',hp.port
            print 'Network Interface:     ',hp.IFACE
            print 'Number of known hosts: ',len(hp.ENUM_HOSTS)
            print 'UPNP Version:          ',hp.UPNP_VERSION
            print 'Debug mode:            ',hp.DEBUG
            print 'Verbose mode:          ',hp.VERBOSE
            print 'Show only unique hosts:',hp.UNIQ
            print 'Using log file:        ',hp.LOG_FILE
            return

    showHelp(argv[0])
    return


#Debug, disabled by default
def debug(argc,argv,hp):
    command = ''
    if hp.DEBUG == False:
        print 'Debug is disabled! To enable, try the seti command...'
        return
    if argc == 1:
        showHelp(argv[0])
    else:
        for cmd in argv[1:]:
            command += cmd + ' '
        command = command.strip()
        print eval(command)
    return
#Quit!
def exit(argc,argv,hp):
    quit(argc,argv,hp)

#Quit!
def quit(argc,argv,hp):
    if argc == 2 and argv[1] == 'help':
        showHelp(argv[0])
        return
    print 'Bye!'
    print ''
    hp.cleanup()
    sys.exit(0)

################ End Action Functions ######################

#Toggle boolean values
def toggleVal(val):
    if val:
        return False
    else:
        return True

#Prompt for user input
def getUserInput(hp,shellPrompt):
    defaultShellPrompt = 'upnp> '
    if shellPrompt == False:
        shellPrompt = defaultShellPrompt

    try:
        uInput = raw_input(shellPrompt).strip()
        argv = uInput.split()
        argc = len(argv)
    except KeyboardInterrupt, e:
        print '\n'
        if shellPrompt == defaultShellPrompt:
            quit(0,[],hp)
        return (0,None)
    if hp.LOG_FILE != False:
        try:
            hp.LOG_FILE.write("%s\n" % uInput)
        except:
            print 'Failed to log data to log file!'

    return (argc,argv)
