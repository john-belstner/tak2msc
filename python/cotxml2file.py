#!/usr/bin/python
#
#
#  cotxml2file - CoT XML to File                          General Public License v2
#
#  (C)2024-2025 John Belstner
#
#  This software will listen for Cursor-On-Target (CoT) XML formatted messages from 
#  the Tactical Awareness Kit (TAK) program, and save them to an XML file.
# 
#  Acknowledgements:
#      Tactical Awareness Kit (TAK) - https://tak.gov
#      The takproto project by Sensors & Signals LLC - https://github.com/snstac/takproto
#      Military Standard Communications (MSC) software suite - https://www.usarmymars.org/resources/software
#

# Libraries
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import socket
import signal
import time
import os

# Specific constants
VERSION = 1.0
UDP_IP = '127.0.0.1'
UDP_PORT = 6969
BUFFER_SIZE = 2048
XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
EVENT_HEADER = '<event version="2.0" '


# Setup a socket for receiving multicast messages
def setup_socket(buffer_size):
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(1.0)
    # Allow multiple sockets to use the same port number
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Bind the socket to the port
    sock.bind((UDP_IP, UDP_PORT))
    return sock


# Check if the received data is a CoT xml event message
def is_cot_xml(xml_string):
    if XML_HEADER in xml_string and EVENT_HEADER in xml_string:
        return True
    else:
        return False


# Save the XML string to a file
def save_xml_to_file(xml_string, filename):
    with open(filename, 'wb') as file:
        file.write(str.encode(xml_string))


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
    # Print the program version
    print('\ncotxml2file - CoT XML to File v' + str(VERSION) + '\n')
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
            # Check if the received data is a CoT xml message
            if not is_cot_xml(data.decode('utf-8')):
                continue
            # Split the CoT xml message into two lines
            xml = data.decode("utf-8").split('\n')
            # Extract the callsign text from the CoT xml message
            callsign = xml[1].split('callsign=')[1].split('"')[1]
            # Save the XML event to a file
            filename = 'CoT-' + callsign + '-' + datetime.now().strftime('%Y%m%dT%H%M%S') + '.xml'
            save_xml_to_file(xml[1], filename)
            # Print the filename
            print('Saving ' + filename)
