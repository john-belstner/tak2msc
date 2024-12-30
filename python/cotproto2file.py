#!/usr/bin/python
#
#
#  cotproto2file - CoT Protobuf to XML File              General Public License v2
#
#  (C)2024-2025 John Belstner
#
#  This software will listen for Cursor-On-Target (CoT) protobuf messages from the 
#  Tactical Awareness Kit (TAK) program, convert them to XML text format, and save
#  them to an XML file.
# 
#  Acknowledgements:
#      Tactical Awareness Kit (TAK) - https://tak.gov
#      The takproto project by Sensors & Signals LLC - https://github.com/snstac/takproto
#      Military Standard Communications (MSC) software suite - https://www.usarmymars.org/resources/software
#

# Libraries
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import takproto
import socket
import struct
import signal
import time
import os

# Specific constants
VERSION = 1.0
MCAST_GRP = '239.2.3.1'
MCAST_PORT = 6969
LISTEN_ALL_GROUPS = False
BUFFER_SIZE = 2048
PROTOBUF_HEADER = [0xbf, 0x01, 0xbf]


# Setup a socket for receiving multicast messages
def setup_socket(buffer_size):
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(1.0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if LISTEN_ALL_GROUPS:
        # on this port, receives ALL multicast groups
        sock.bind(('', MCAST_PORT))
    else:
        # on this port, listen ONLY to MCAST_GRP
        sock.bind((MCAST_GRP, MCAST_PORT))
    # Tell the kernel that we want to add ourselves to a multicast group
    mreq = struct.pack('4sl', socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return sock


# Check if the received data is a CoT protobuf message
def is_cot_protobuf(data):
    if (data[0] == PROTOBUF_HEADER[0] and data[1] == PROTOBUF_HEADER[1] and data[2] == PROTOBUF_HEADER[2]):
        return True
    else:
        return False


# Parse the received CoT event and return an XML element tree
def cot_to_xml(cot):
    # Create the XML tree
    event = ET.Element('event')
    point = ET.SubElement(event, 'point')
    detail = ET.SubElement(event, 'detail')
    contact = ET.SubElement(detail, 'contact')
    # Add the CoT event data to the XML tree
    event.set('version', '2.0')
    event.set('uid', cot.cotEvent.uid)
    event.set('type', cot.cotEvent.type)
    event.set('time', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + 'Z')
    event.set('start', datetime.fromtimestamp(cot.cotEvent.startTime/1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + 'Z')
    event.set('stale', datetime.fromtimestamp(cot.cotEvent.staleTime/1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + 'Z')
    event.set('how', cot.cotEvent.how)
    event.set('access', cot.cotEvent.access)
    # Add the CoT point data to the XML tree
    point.set('lat', str(cot.cotEvent.lat))
    point.set('lon', str(cot.cotEvent.lon))
    point.set('hae', str(cot.cotEvent.hae))
    point.set('ce', str(cot.cotEvent.ce))
    point.set('le', str(cot.cotEvent.le))
    # Event specific XML data that was not protobuf encoded was sent
    # as a string in the "xmlDetail" field of the CoT event message.
    # We parse this string and add it to the XML tree.
    xmlDetails = cot.cotEvent.detail.xmlDetail.split('><')
    # The split method removes the delimiters, so we add them back
    for x in range(len(xmlDetails)):
        if (xmlDetails[x][0] != '<'):
            xmlDetails[x] = '<' + xmlDetails[x]
        if (xmlDetails[x][-1] != '>'):
            xmlDetails[x] = xmlDetails[x] + '>'
    # Add the XML detail data to the XML tree
    for xml in xmlDetails:
        element = ET.fromstring(xml)
        detail.append(element)
    # Add the contact data to the XML tree
    contact.set('callsign', cot.cotEvent.detail.contact.callsign)
    contact.set('endpoint', cot.cotEvent.detail.contact.endpoint)   
    # Add the group data to the XML tree if it exists
    if cot.cotEvent.detail.HasField('group'):
        group = ET.SubElement(detail, 'group')
        group.set('name', cot.cotEvent.detail.group.name)
        group.set('role', cot.cotEvent.detail.group.role)
    # Add precision location data to the XML tree if it exists
    if cot.cotEvent.detail.HasField('precisionLocation'):
        precisionLocation = ET.SubElement(detail, 'precisionLocation')
        precisionLocation.set('altsrc', cot.cotEvent.detail.precisionLocation.altsrc)
        precisionLocation.set('geopointsrc', str(cot.cotEvent.detail.precisionLocation.geopointsrc))
    # Add the status data to the XML tree if it exists
    if cot.cotEvent.detail.HasField('status'):
        status = ET.SubElement(detail, 'status')
        status.set('battery', str(cot.cotEvent.detail.status.battery))
    # Add the takv data to the XML tree if it exists
    if cot.cotEvent.detail.HasField('takv'):
        takv = ET.SubElement(detail, 'takv')
        takv.set('device', cot.cotEvent.detail.takv.device)
        takv.set('platform', cot.cotEvent.detail.takv.platform)
        takv.set('os', cot.cotEvent.detail.takv.os)
        takv.set('version', cot.cotEvent.detail.takv.version)
    # Add the track data to the XML tree if it exists
    if cot.cotEvent.detail.HasField('track'):
        track = ET.SubElement(detail, 'track')
        track.set('course', str(cot.cotEvent.detail.track.course))
        track.set('speed', str(cot.cotEvent.detail.track.speed))
    # Return the XML tree
    return event


# Save the XML tree to a file
def save_xml_tree(tree, filename):
    with open(filename, 'wb') as file:
        file.write(ET.tostring(tree, encoding='utf-8', method='xml'))


# Ctrl-c handler
def signal_handler(signal, frame):
    print(">>> Ctrl+C detected, exiting...")
    # Close the socket
    sock.close()
    time.sleep(2)   # Wait for the socket to close
    os._exit(0)


# Register the ctrl-c signal handler
signal.signal(signal.SIGINT, signal_handler)


# Main program
if __name__ == '__main__':
    print('\ncotproto2file - CoT Protobuf to XML File v' + str(VERSION) + '\n')
    # Setup the socket
    sock = setup_socket(BUFFER_SIZE)
    # Loop
    while True:
        # Wait for a CoT event
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            continue
        else:
            # Check if the received data is a CoT protobuf message
            if not is_cot_protobuf(data):
                continue
            # Parse the CoT protobuf message
            cot = takproto.parse_proto(data)
            # Check if the CoT protobuf message has an event
            if not cot.HasField('cotEvent'):
                continue
            # Convert the CoT protobuf event to an XML tree
            event = cot_to_xml(cot)
            # Save the XML tree to a file
            filename = 'CoT-' + cot.cotEvent.detail.contact.callsign + '-' + datetime.now().strftime('%Y%m%dT%H%M%S') + '.xml'
            save_xml_tree(event, filename)
            # Print the filename
            print('Saving ' + filename)
