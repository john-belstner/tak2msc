#!/usr/bin/python
#
#
#  tak2mm - WinTAK CoT XML to Message Machine                    General Public License v2
#
#  (C)2024-2025 John Belstner
#
#  This software will listen for Cursor-On-Target (CoT) XML formatted messages from the
#  Windows Tactical Awareness Kit (WinTAK) program, and send them to Message Machine in
#  an ACP-127 formatted message. The Message Creator is used to select the addressing and
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
import xml.etree.ElementTree as ET


# Application specific constants
VERSION = 0.5
LOCALHOST = '127.0.0.1'
TAK_MCAST_GROUP = '239.2.3.1'
TAK_MCAST_PORT = 6969
TAK_COTXML_PORT = 10001
TAK_DEFAULT_PORT = 4242
BUFFER_SIZE = 2048
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
EVENT_HEADER = '<event version="2.0" '
MSG_MACHINE_PORT = 5003
SA_EVENT_TYPE = 'type="a-f-G-U-C'
PD_EVENT_TYPE = 'parent_callsign='
IMPORTS_PATH = 'C:/MSC/MessageMachine64/imports'
TAK2MSC_PATH = 'C:/MSC/MessageMachine64/imports/tak2msc'
CP_TCP_PORT = 5001
DEBUG = False  # Set to True to enable debug messages


# Global variables
started = False
data_from_cp = ''
myPosition_event = ''
pointDropper_event = ''
messageCreator_file = ''
lines = []


# Debug print function
# This function is used to print debug messages to the console.
def debugPrint(msg):
    if DEBUG:
        print(msg)


# This function removes all files in the tak2msc directory
def remove_old_files():
    print("Removing old files in the tak2msc directory...")
    for filename in os.listdir(TAK2MSC_PATH):
        file_path = os.path.join(TAK2MSC_PATH, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
            continue


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


# Define the CoT XML Listener thread
# This is a separate thread that listens for incoming CoT XML messages
def cotXmlListener(name):
    global data_from_cp, myPosition_event, pointDropper_event
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
            if not EVENT_HEADER in data_string:
                continue
            # Split the CoT xml message into two lines
            # The first line is just an xml header and the second line is the CoT event
            xml = data_string.split('\n')
            # Check if the received data is a CoT xml SA event message or a point dropper
            # event message and update the corresponding status entry field
            if PD_EVENT_TYPE in xml[1] and pointDropper_event == '':
                print("Received new Point Dropper CoT XML event...")
                pointDropper_event = xml[1]
            elif SA_EVENT_TYPE in xml[1] and myPosition_event == '':
                print("Received new Potition Update CoT XML event...")
                myPosition_event = xml[1]
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
    global data_from_cp
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
                debugPrint("Received " + str(len(records)) + " XML records from CP...")
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
                                elif child.tag == 'PAYLOAD':
                                    for grandchild in child:
                                        if grandchild.tag == 'DATA':
                                            payload_data_from_cp = grandchild.text
                    except Exception as e:
                        print(f"XML Parse Error: {e}")
                        continue

                    if command_ == 'status':
                        debugPrint("Received Status Event from CP...")
                    elif command_ == 'config':
                        debugPrint("Received Config Event from CP...")
                    elif command_ == 'ack':
                        debugPrint("Received Ack Event from CP...")
                    elif command_ == 'data' and COT_EVENT_HEADER in payload_data_from_cp:
                        print("Received CoT XML Data Event from CP...")
                        # Check if the received data is wrapped in an ACP-127 message
                        if 'GENTEXT/REMARKS/' in payload_data_from_cp:
                            # The data is wrapped in an ACP-127 message, so we need to extract it
                            payload_data_from_cp = payload_data_from_cp.split('GENTEXT/REMARKS/')[1]
                            payload_data_from_cp = payload_data_from_cp.split('//')[0]
                            # Add the TAK XML header to the data
                            data_from_cp = TAK_XML_HEADER + '\n' + payload_data_from_cp
                        else:
                            print("The CoT XML Data Event is not wrapped in an ACP-127 message!")
                            continue
        except socket.timeout:
            continue

    print("Exiting CP Listener thread...")
    # Close the tcp socket
    try:
        sock.close()
        return True
    except Exception as e:
        print(e)
        return False


# Define the ACP-127 Template Listener thread
# This is a separate thread that waits for a blank templat to appear in
# the TAK2MSC_PATH. It runs in a loop until the program is terminated.
def templateListener(name):
    global lines, messageCreator_file
    print("Starting Template Listener thread...")

    # Loop
    while started:
        # Check if there are any files in the directory
        if len(os.listdir(TAK2MSC_PATH)) > 0 and len(lines) == 0:
            # Get the first file in the directory
            filename = os.listdir(TAK2MSC_PATH)[0]
            messageCreator_file = os.path.join(TAK2MSC_PATH, filename)
            print("Found " + filename)
            try:
                with open(messageCreator_file, 'r') as file:
                    lines = file.readlines()
            except Exception as e:
                print(f"Error opening file: {e}")
                continue
            # Check if the file is a blank CoT xml event template
            if not is_cot_template(lines):
                # The file is not a blank CoT xml event template, so delete it
                os.remove(messageCreator_file)
                messageCreator_file = ''
                lines = []
                print("File is not a blank CoT xml event template, deleting...")
                break

        time.sleep(1)  # Sleep for a while to avoid busy waiting

    print("Exiting Template Listener thread...")
    # Remove any old template files in the tak2msc directory
    for filename in os.listdir(TAK2MSC_PATH):
        file_path = os.path.join(TAK2MSC_PATH, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
            continue
    return True


# Ctrl-c handler
def signal_handler(signal, frame):
    global started
    print(">>> Ctrl+C detected, exiting...")
    started = False  # Stop the cotXmlListener thread
    time.sleep(2)   # Wait for the sockets to close
    os._exit(0)

# Register the ctrl-c signal handler
signal.signal(signal.SIGINT, signal_handler)


# Main program
if __name__ == '__main__':
    # Print the program version
    print('\ntak2mmm - WinTAK CoT XML capture v' + str(VERSION) + '\n')

    # Check to make sure we can access Message Creator and Message Machine
    if not os.path.exists(IMPORTS_PATH):
        print("MSC installation not found!")
        os.exit(1)
    elif not os.path.exists(TAK2MSC_PATH):
        os.makedirs(TAK2MSC_PATH)

    # Remove any old files in the tak2msc directory
    remove_old_files()

    started = True
    # Start the CoT XML Listener thread
    try:
        cotXmlThread = threading.Thread(target=cotXmlListener, args=(1,))
        cotXmlThread.start()
    except Exception as e:
        print(f"Error starting CoT XML Listener thread: {e}")
        os.exit(1)

    # Start the CP Listener thread
    try:
        cpThread = threading.Thread(target=cpListener, args=(1,))
        cpThread.start()
    except Exception as e:
        print(f"Error starting CP Listener thread: {e}")
        os._exit(1)

    # Start the Template Listener thread
    try:
        templateThread = threading.Thread(target=templateListener, args=(1,))
        templateThread.start()
    except Exception as e:
        print(f"Error starting Template Listener thread: {e}")
        os._exit(1)

    loopCounter = 0
    while started:
        loopCounter += 1

        # Check if the threads are still running
        if not cotXmlThread.is_alive() or not cpThread.is_alive() or not templateThread.is_alive():
            # If any of the threads have stopped, exit the program
            print("One of the threads has stopped, exiting...")
            started = False
            break

        template_exists = len(lines) > 0
        sa_event_exists = myPosition_event != ''
        pd_event_exists = pointDropper_event != ''
        event_ready = False

        # Check if we can send an event message to Message Machine
        if template_exists and sa_event_exists:
            print("Creating an SA Event Message...")
            lines = calculate_digest(lines, myPosition_event)
            myPosition_event = ''
            event_ready = True
        elif template_exists and pd_event_exists:
            print("Creating a Point Dropper Event Message...")
            lines = calculate_digest(lines, pointDropper_event)
            pointDropper_event = ''
            event_ready = True

        if event_ready:
            # Write the lines back to the file
            try:
                with open(messageCreator_file, 'w') as file:
                    file.writelines(lines)
                # Move the file to the Message Machine import directory
                print("Moving completed message to Message Machine...")
                shutil.move(messageCreator_file, IMPORTS_PATH)
                messageCreator_file = ''
                lines = []  # Clear the lines list
            except Exception as e:
                print(f"Error writing/moving file: {e}")
                remove_old_files()
                messageCreator_file = ''
                lines = []  # Clear the lines list
                continue

        # Print debug messages every 60 seconds
        if loopCounter % 60 == 0:
            debugPrint('DEBUG - tak2mm is running...')

        time.sleep(1)  # Sleep for a while to avoid busy waiting




