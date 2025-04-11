#!/usr/bin/python
#
#
#  tak2msc-nogui - WinTAK CoT XML to Message Machine           General Public License v2
#
#  (C)2024-2025 John Belstner
#
#  This software will listen for Cursor-On-Target (CoT) XML formatted messages from the
#  Windows Tactical Awareness Kit (WinTAK) program, and send them to Message Machine in
#  an ACP-127 formatted message. The GUI will allow the user to select the addressing and
#  conditions for the message. This software is intended for use with the Military Standard
#  Communications (MSC) software suite, and is not intended for use with any other software.
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
import shutil
import hashlib
import threading
import configparser


# Application specific constants
VERSION = 0.2
LOCALHOST = '127.0.0.1'
COTXML_PORT = 10001
BUFFER_SIZE = 2048
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
EVENT_HEADER = '<event version="2.0" '
MSG_MACHINE_PORT = 5003
SA_EVENT_TYPE = 'type="a-f-G-U-C'
PD_EVENT_TYPE = 'parent_callsign='
MC_CONFIG_FILE = 'C:/MSC/MessageCreator64/messagecreator.ini'
IMPORTS_PATH = 'C:/MSC/MessageMachine64/imports'
TAK2MSC_PATH = 'C:/MSC/MessageMachine64/imports/tak2msc'

# Global variables
started = False
myPosition_event = ''
pointDropper_event = ''


# Check if the specified list is a blank CoT xml event template
# This function is called from the main program
def is_cot_template(lines):
    cotXmlSubject = False
    blankRemarks = False
    for line in lines:
        if 'SUBJ/COTXML//' in line:
            cotXmlSubject = True
        if 'GENTEXT/REMARKS/-//' in line:
            blankRemarks = True
    if cotXmlSubject and blankRemarks:
        return True
    else:
        return False

# Check if the specified list is a blank CoT xml event template
# This function is called from the main program
def calculate_digest(lines, cotString):
    bigString = ''
    digest = ''
    startOfString = False
    endOfString = False
    pastClassifier = False
    for i in range(len(lines)):
        if not startOfString and not endOfString:
            # Look for the start of the string
            if 'BT\n' in lines[i]:
                startOfString = True
        elif startOfString and not endOfString and not pastClassifier:
            # The classifier is the first line after the BT
            pastClassifier = True
        elif startOfString and not endOfString and pastClassifier:
            if 'BT\n' in lines[i]:
                # We found the end of what is digested
                endOfString = True
            elif 'GENTEXT/REMARKS/-//' in lines[i]:
                # Insert the cotString into the line
                lines[i] = 'GENTEXT/REMARKS/' + cotString + '//' + '\n'
                bigString += lines[i].replace('\n', ' ')
            else:
                # Add the line to the string
                bigString += lines[i].replace('\n', ' ')
        elif startOfString and endOfString:
            if '[DIGEST:' in lines[i]:
                bigString = ' '.join(bigString.split())
                digest = hashlib.md5(bytes(bigString, 'utf-8')).hexdigest().upper()
                lines[i] = '[DIGEST:' + digest + ']\n'

    # Return the list of lines with new digest filled in
    return lines

# Check if the received data is a CoT xml event message
# This function is called from inside the cotXMLListener thread
def is_cot_xml(xml_string):
    if EVENT_HEADER in xml_string:
        return True
    else:
        return False

# Check if the received data is a CoT xml SA event message
# This function is called from inside the cotXMLListener thread
def is_sa_event(xml_string):
    if SA_EVENT_TYPE in xml_string:
        return True
    else:
        return False

# Check if the received data is a CoT xml PD event message
# This function is called from inside the cotXMLListener thread
def is_pd_event(xml_string):
    if PD_EVENT_TYPE in xml_string:
        return True
    else:
        return False

# Define the CoT XML Listener thread
# This is a separate thread that listens for incoming CoT XML messages
def cotXmlListener(name):
    global started, myPosition_event, pointDropper_event
    print("Starting CoT XML Listener thread...")
    try:
        # Create a UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(1.0)
        # Allow multiple sockets to use the same port number
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind the socket to the port
        sock.bind((LOCALHOST, COTXML_PORT))
    except socket.error as e:
        print(f"Socket error: {e}")
        os.exit(1)

    # Loop
    while started:
        # Wait for a CoT event
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            # Check if the received data is a CoT xml message
            data_string = data.decode("utf-8")
            print(data_string)
            if not is_cot_xml(data_string):
                continue
            # Split the CoT xml message into two lines
            # The first line is just an xml header and the second line is the CoT event
            xml = data_string.split('\n')
            # Check if the received data is a CoT xml SA event message or a point dropper
            # event message and update the corresponding status entry field
            if is_pd_event(xml[1]) and pointDropper_event == '':
                print("Received new Point Dropper CoT XML event...")
                pointDropper_event = xml[1]
            elif is_sa_event(xml[1]) and myPosition_event == '':
                print("Received new Potition Update CoT XML event...")
                myPosition_event = xml[1]
        except socket.timeout:
            continue

    print("Exiting CoT XML Listener thread...")
    # Close the udp socket
    try:
        sock.close()
        return True
    except Exception as e:
        print(e)
        return False


# Ctrl-c handler
def signal_handler(signal, frame):
    print(">>> Ctrl+C detected, exiting...")
    started = False  # Stop the cotXmlListener thread
    time.sleep(2)   # Wait for the socket to close
    os._exit(0)

# Register the ctrl-c signal handler
signal.signal(signal.SIGINT, signal_handler)


# Main program
if __name__ == '__main__':
    # Print the program version
    print('\ntak2msc-nogui - WinTAK CoT XML capture v' + str(VERSION) + '\n')

    # Check to make sure we can access Message Creator and Message Machine
    if not os.path.exists(IMPORTS_PATH):
        print("MSC installation not found!")
        os.exit(1)
    elif not os.path.exists(TAK2MSC_PATH):
        os.makedirs(TAK2MSC_PATH)

    # Start the CoT XML Listener thread
    started = True
    try:
        cotXmlThread = threading.Thread(target=cotXmlListener, args=(1,))
        cotXmlThread.start()
    except Exception as e:
        print(f"Error starting CoT XML Listener thread: {e}")
        os.exit(1)

    # Remove any old files in the tak2msc directory
    print("Removing old files in the tak2msc directory...")
    for filename in os.listdir(TAK2MSC_PATH):
        file_path = os.path.join(TAK2MSC_PATH, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
            continue

    # Wait for a blank ACP-127 message from Message Creator
    while started:
        if len(os.listdir(TAK2MSC_PATH)) > 0 and (myPosition_event != '' or pointDropper_event != ''):
            # Get the first file in the directory
            filename = os.listdir(TAK2MSC_PATH)[0]
            messageCreator_file = os.path.join(TAK2MSC_PATH, filename)
            lines = []
            try:
                with open(messageCreator_file, 'r') as file:
                    lines = file.readlines()
            except Exception as e:
                print(f"Error opening file: {e}")
                continue
            # Read the file and check if it is a blank CoT xml event template
            if is_cot_template(lines):
                if pointDropper_event != '':
                    print("Creating a Point Dropper Event Message...")
                    lines = calculate_digest(lines, pointDropper_event)
                    pointDropper_event = ''
                elif myPosition_event != '':
                    print("Creating an SA Event Message...")
                    lines = calculate_digest(lines, myPosition_event)
                    myPosition_event = ''
                else:
                    print("No CoT XML event received!")
                    continue
                # Write the lines back to the file
                try:
                    with open(messageCreator_file, 'w') as file:
                        file.writelines(lines)
                except Exception as e:
                    print(f"Error writing file: {e}")
                    continue

                # Move the file to the Message Machine import directory
                print("Moving completed message to Message Machine...")
                shutil.move(messageCreator_file, IMPORTS_PATH)
            else:
                # The file is not a blank CoT xml event template, so delete it
                os.remove(messageCreator_file)
                print("File is not a blank CoT xml event template, deleting...")

        elif len(os.listdir(TAK2MSC_PATH)) > 0:
            print("Waiting for a CoT xml event from WinTAK...")
        else:
            print("Waiting for blank message from MessageCreator...")

        time.sleep(5)  # Sleep for a while to avoid busy waiting




