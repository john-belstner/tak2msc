#!/usr/bin/python
#
#
#  tak2cpi - WinTAK CoT XML to Communication Processor (CP)      General Public License v2
#
#  (C)2024-2025 John Belstner
#
#  This software will listen for Cursor-On-Target (CoT) XML formatted messages from the
#  Windows Tactical Awareness Kit (WinTAK) program, and send them directly to CP as a chat
#  message. This software is intended for use with Military Standard Communications (MSC)
#  software suite, and is not intended for use with any other software.
# 
#  Acknowledgements:
#      Tactical Awareness Kit (TAK) - https://tak.gov
#      The takproto project by Sensors & Signals LLC - https://github.com/snstac/takproto
#      Military Standard Communications (MSC) software suite - https://www.usarmymars.org/resources/software
#

# Libraries
import os
import time
import socket
import signal
import threading
import xml.etree.ElementTree as ET


# User configurable constants
# These constants are used to configure the program and should be set by the user
# before running the program.
SOURCE_STATION = 'AAR9EN'  # Your callsign goes here
DESTINATION_STATION = 'ORANGEMAIN'  # TAK Gateway Station callsign here


# Application specific constants
VERSION = 0.3
LOCALHOST = '127.0.0.1'
TAK_MCAST_GROUP = '239.2.3.1'
TAK_MCAST_PORT = 6969
TAK_COTXML_PORT = 10001
TAK_DEFAULT_PORT = 4242
BUFFER_SIZE = 2048
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
TAK_XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
COT_EVENT_HEADER = '<event version="2.0" '
CP_TCP_PORT = 5001
DEBUG = False  # Set to True to enable debug messages


# Global variables
started = False
data_from_cp = ''
data_to_cp = ''
modemDataRate = ''
modemInterleave = ''
modemWaveform = ''
keyList = []


# Create the XML document used by CP
v3protocol = ET.Element('V3PROTOCOL')
header = ET.SubElement(v3protocol, 'HEADER')
positionId = ET.SubElement(header, 'POSITIONID')
command = ET.SubElement(header, 'COMMAND')
priority = ET.SubElement(header, 'PRIORITY')
compress = ET.SubElement(header, 'COMPRESS')
encrypt = ET.SubElement(header, 'ENCRYPT')
encryptionKey = ET.SubElement(header, 'ENCRYPTIONKEY')
sourceStation = ET.SubElement(header, 'SOURCESTATION')
destinationStation = ET.SubElement(header, 'DESTINATIONSTATION')
aleAddress = ET.SubElement(header, 'ALEADDRESS')
modemDataRate = ET.SubElement(header, 'MODEMDATARATE')
modemInterleave = ET.SubElement(header, 'MODEMINTERLEAVE')
checksum = ET.SubElement(header, 'CHECKSUM')
payload = ET.SubElement(v3protocol, 'PAYLOAD')
data = ET.SubElement(payload, 'DATA')
# Set default values for the XML elements
positionId.text = 'MessageMachine'
command.text = 'data'
priority.text = '4' # 0 = no priority, 1 = high priority
compress.text = '1' # 0 = no compress, 1 = compress
encrypt.text = '1' # 0 = no encrypt, 1 = encrypt
encryptionKey.text = 'ZYG25A'
sourceStation.text = SOURCE_STATION
destinationStation.text = DESTINATION_STATION
checksum.text = 'PASS'


# Debug print function
# This function is used to print debug messages to the console.
def debugPrint(msg):
    if DEBUG:
        print(msg)


# Define the CoT XML Listener thread
# This is a separate thread that listens for CoT XML messages sent from WinTAK
# and processes them. It runs in a loop until the program is terminated.
def cotXmlListener(name):
    global started, data_to_cp, data_from_cp
    print("Starting CoT XML Listener thread...")
    try:
        # Create a UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(1.0)
        # Allow multiple sockets to use the same port number
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind the socket to the port
        sock.bind((LOCALHOST, TAK_COTXML_PORT))
    except socket.error as e:
        print(f"Socket error opening TAK CoT port: {e}")
        os._exit(1)

    # Loop
    while started:
        # Wait for a CoT event
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            # Check if the received data is a CoT xml message
            data_string = data.decode("utf-8")
            debugPrint(data_string)
            if not COT_EVENT_HEADER in data_string:
                continue
            print("Received a new CoT XML event...")
            # Split the CoT xml message into two lines
            # The first line is just an xml header and the second line is the CoT event
            # No need to send the xml header over the air
            xml = data_string.split('\n')
            data_to_cp = xml[1]

        except socket.timeout:
            # Check for something to send to WinTAK
            if data_from_cp != '':
                # Send the data to WinTAK
                try:
                    print("Sending CoT XML Data to WinTAK...")
                    sock.sendto(data_from_cp.encode('utf-8'), (LOCALHOST, TAK_DEFAULT_PORT))
                    data_from_cp = ''
                except socket.error as e:
                    print(f"Failed sending CoT XML Data to WinTAK: {e}")
                    data_from_cp = ''
                    continue
            continue

    print("Exiting CoT XML Listener thread...")
    # Close the udp socket
    try:
        sock.close()
        return True
    except Exception as e:
        print(e)
        return False


# Define the CP Listener thread
# This is a separate thread that listens for incoming messages sent from CP
# and processes them. It runs in a loop until the program is terminated.
def cpListener(name):
    global v3protocol, data_from_cp, data_to_cp, encryptionKey, data, keyList, modemDataRate, modemInterleave
    print("Starting CP Listener thread...")
    try:
        # Create a TCP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        # Bind the socket to the port
        sock.connect((LOCALHOST, CP_TCP_PORT))
    except socket.error as e:
        print(f"Socket error connecting to CP: {e}")
        os._exit(1)

    # Loop
    while started:
        # Wait for a CP event
        try:
            data_ = sock.recv(BUFFER_SIZE)
            # Check if the received data is an xml message
            data_string = data_.decode("utf-8")
            payload_data_from_cp = ''
            debugPrint(data_string)
            if XML_HEADER in data_string:
                xml_strings = data_string.split(XML_HEADER)
                # data_string begins with an XML_HEADER, so the first string in xml_strings is empty
                records = xml_strings[1:]
                print("Received " + str(len(records)) + " XML records from CP...")
                for record in records:
                    command_ = ''
                    try:
                        root = ET.fromstring(record)
                        if root.tag == 'V3PROTOCOL':
                            for child in root:
                                if child.tag == 'HEADER':
                                    for grandchild in child:
                                        if grandchild.tag == 'COMMAND':
                                            command_ = grandchild.text
                                        elif grandchild.tag == 'MODEMDATARATE':
                                            modemDataRate = grandchild.text
                                        elif grandchild.tag == 'MODEMINTERLEAVE':
                                            modemInterleave = grandchild.text
                                        elif grandchild.tag == 'KEYLIST':
                                            keyList = grandchild.text.split(',')
                                            encryptionKey.text = keyList[0]
                                elif child.tag == 'PAYLOAD':
                                    for grandchild in child:
                                        if grandchild.tag == 'DATA':
                                            payload_data_from_cp = grandchild.text
                    except Exception as e:
                        print(f"XML Parse Error: {e}")
                        continue

                    if command_ == 'status':
                        print("Received Status Event from CP...")
                        print(f"    Data Rate: {modemDataRate}")
                        print(f"    Interleave: {modemInterleave}")
                    elif command_ == 'config':
                        print("Received Config Event from CP...")
                        print(f"    Key List: {keyList}")
                    elif command_ == 'ack':
                        print("Received Ack Event from CP...")
                    elif command_ == 'data' and COT_EVENT_HEADER in payload_data_from_cp:
                        print("Received CoT XML Data Event from CP...")
                        data_from_cp = TAK_XML_HEADER + '\n' + payload_data_from_cp

        except socket.timeout:
            # Check for data to send to CP
            if data_to_cp != '':
                # Copy the data to the V3PROTOCOL XML document
                data.text = data_to_cp
                xml_string = ET.tostring(v3protocol, encoding='unicode')
                xml_string = XML_HEADER + '\n' + xml_string
                try:
                    print("Sending CoT XML Data to CP for transmit...")
                    sock.sendall(xml_string.encode() + b'\n')
                    data_to_cp = ''
                except Exception as e:
                    print(f"Error sending to CP: {e}")
                    data_to_cp = ''
                    continue
            continue

    print("Exiting CP Listener thread...")
    # Close the tcp socket
    try:
        sock.close()
        return True
    except Exception as e:
        print(e)
        return False


# Ctrl-c handler
def signal_handler(signal, frame):
    global started
    print(">>> Ctrl+C detected, exiting...")
    started = False  # Stop the cotXmlListener thread
    time.sleep(3)   # Wait for the sockets to close
    os._exit(0)

# Register the ctrl-c signal handler
signal.signal(signal.SIGINT, signal_handler)


# Main program
if __name__ == '__main__':
    # Print the program version
    print('\ntak2cp - WinTAK CoT XML capture v' + str(VERSION) + '\n')
    started = True

    # Start the CoT XML Listener thread
    try:
        cotXmlThread = threading.Thread(target=cotXmlListener, args=(1,))
        cotXmlThread.start()
    except Exception as e:
        print(f"Error starting CoT XML Listener thread: {e}")
        os._exit(1)

    # Start the CP Listener thread
    try:
        cpThread = threading.Thread(target=cpListener, args=(1,))
        cpThread.start()
    except Exception as e:
        print(f"Error starting CP Listener thread: {e}")
        os._exit(1)

    loopCounter = 0
    while started:
        loopCounter += 1
        # Check if the threads are still running
        if not cotXmlThread.is_alive() or not cpThread.is_alive():
            print("One of the threads has stopped, exiting...")
            started = False
            break
        # Print debug messages every 60 seconds
        if loopCounter % 60 == 0:
            debugPrint('DEBUG - tak2cp is running...')

        time.sleep(1)  # Sleep for a while to avoid busy waiting
