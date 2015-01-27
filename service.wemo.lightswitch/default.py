#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import os
import sys
import datetime
import xbmc
import xbmcaddon

__addon__ = xbmcaddon.Addon()
__cwd__ = __addon__.getAddonInfo('path')
__resource__ = xbmc.translatePath(os.path.join(__cwd__, 'resources', 'lib'))
__resource__ = __resource__.decode("UTF-8")

sys.path.append(__resource__)

wemoIP = __addon__.getSetting('hostname')
wemoPort = 49153

from miranda import upnp, msearch
SWITCHES = []
xbmc.log("WeMo Light: Initializing")

def should_turn_on():
    """
    Checks to see if the lights should turn on at this time

    If the "disable at a certain time" setting is enabled, this returns false during the specified time range
    """
    disableOn = __addon__.getSetting('disableOn') == 'true'
    if (not disableOn):
        return True
    from_time = int(__addon__.getSetting("fromTime"))
    to_time = int(__addon__.getSetting("toTime"))
    now_hour = datetime.datetime.now().hour
    if (from_time == to_time):
        if now_hour == from_time:
            return False
    elif from_time < to_time:
        if (now_hour >= from_time) and (now_hour < to_time):
            return False
    else:
        if (now_hour >= from_time) or (now_hour < to_time):
            return False
    return True

def _send(action, args=None):
    """
    Send a command to the switch
    """
    xbmc.log("WeMo Light: Sending action %s" % action)
    if not args:
        args = {}
    host_info = conn.ENUM_HOSTS[SWITCHES[0]]
    if ('controllee' in hostInfo['deviceList']):
        device_name = 'controllee'
    else:
        device_name = 'lightswitch'
    service_name = 'basicevent'
    controlURL = host_info['proto'] + host_info['name']
    controlURL2 = hostInfo['deviceList'][device_name]['services'][service_name]['controlURL']
    if not controlURL.endswith('/') and not controlURL2.startswith('/'):
        controlURL += '/'
    controlURL += controlURL2

    resp = conn.sendSOAP(
        host_info['name'],
        'urn:Belkin:service:basicevent:1',
        controlURL,
        action,
        args
    )
    return resp

def get():
    """
    Gets the value of the switch
    """
    resp = _send('GetBinaryState')
    tagValue = conn.extractSingleTag(resp, 'BinaryState')
    return True if tagValue == '1' else False

def on():
    """
    Turns on the switch

    BinaryState is set to 'Error' in the case that it was already on.
    """
    resp = _send('SetBinaryState', {'BinaryState': (1, 'Boolean')})
    tagValue = conn.extractSingleTag(resp, 'BinaryState')
    return True if tagValue in ['1', 'Error'] else False

def off():
    """
    Turns off the switch

    BinaryState is set to 'Error' in the case that it was already off.
    """
    resp = _send('SetBinaryState', {'BinaryState': (0, 'Boolean')})
    tagValue = conn.extractSingleTag(resp, 'BinaryState')
    return True if tagValue in ['0', 'Error'] else False

def toggle():
    """
    Toggle the state of the switch
    """
    is_on = get()
    if is_on:
        xbmc.log("WeMo Light: Turn OFF")
        off()
    else:
        xbmc.log("WeMo Light: Turn ON")
        on()


class PlayerMonitor(xbmc.Player):

    def onPlayBackStarted(self):
        # Will be called when xbmc starts playing a file
        is_enabled = __addon__.getSetting("onPlayBackStarted") == "true"
        if is_enabled:
            off()

    def onPlayBackStopped(self):
        # Will be called when user stops xbmc playing a file
        is_enabled = __addon__.getSetting("onPlayBackStopped") == "true"
        if is_enabled and should_turn_on():
            on()

    def onPlayBackEnded(self):
        # Will be called when xbmc stops playing a file
        is_enabled = __addon__.getSetting("onPlayBackEnded") == "true"
        if is_enabled and should_turn_on():
            on()

    def onPlayBackPaused(self):
        # Will be called when user pauses a playing file
        is_enabled = __addon__.getSetting("onPlayBackPaused") == "true"
        if is_enabled and should_turn_on():
            on()

    def onPlayBackResumed(self):
        # Will be called when user resumes a paused file
        is_enabled = __addon__.getSetting("onPlayBackResumed") == "true"
        if is_enabled:
            off()


if __name__ == "__main__":
    conn = upnp()
    # Build phony response
    data = "HTTP/1.1 200 OK\r\n"\
        "LOCATION: http://%s:%d/setup.xml\r\n"\
        "SERVER: Unspecified, UPnP/1.0, Unspecified" % (wemoIP, wemoPort)
    conn.parseSSDPInfo(data,False,False)

    index = 0
    hostInfo = conn.ENUM_HOSTS[index]
    if hostInfo['dataComplete'] == False and not xbmc.abortRequested:
        xbmc.log("WeMo Light: Getting XML for index %d " % index)
        xmlHeaders, xmlData = conn.getXML(hostInfo['xmlFile'])
        conn.getHostInfo(xmlData,xmlHeaders,index)

    #xbmc.log("WeMo Light: Device: %s" % conn.ENUM_HOSTS[index])
    try:
        modelName = ''
        friendlyName = ''
        if ('controllee' in hostInfo['deviceList']):
            # Socket
            modelName = conn.ENUM_HOSTS[index]['deviceList']['controllee']['modelName']
            friendlyName = conn.ENUM_HOSTS[index]['deviceList']['controllee']['friendlyName']
        elif ('lightswitch' in hostInfo['deviceList']):
            # Light Switch
            modelName = conn.ENUM_HOSTS[index]['deviceList']['lightswitch']['modelName']
            friendlyName = conn.ENUM_HOSTS[index]['deviceList']['lightswitch']['friendlyName']

        if modelName != '':
            xbmc.log("WeMo Light: Found WeMo device %s:%s" % (modelName, friendlyName))
            xbmc.executebuiltin("Notification(WeMo Light Switch, Found WeMo device \"%s\". Now it should work!, 20000)" % friendlyName)
            SWITCHES = [index]
    except KeyError:
        pass

    xbmc.executebuiltin("Skin.SetString(wemo, False)")
    xbmc.log("WeMo Light: Starting player monitor")
    player_monitor = PlayerMonitor()
    while not xbmc.abortRequested:
        xbmc.sleep(200)
        to_toggle = xbmc.getInfoLabel("skin.string(wemo)")
        if to_toggle == 'True':
            xbmc.executebuiltin("Skin.SetString(wemo, False)")
            toggle()
