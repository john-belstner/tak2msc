#!/usr/bin/python
#
#
#  tak2msc - WinTAK CoT XML to Message Machine                General Public License v2
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
import time
import socket
import hashlib
import threading
import configparser
import pandas as pd
from tkinter import *
from tkinter import filedialog
from tkinter import messagebox
from datetime import datetime, timezone
import xml.etree.ElementTree as ET


# Application specific constants
APP_VERSION = 0.1
LOCALHOST = '127.0.0.1'
COTXML_PORT = 10001
BUFFER_SIZE = 2048
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
EVENT_HEADER = '<event version="2.0" '
MSG_MACHINE_PORT = 5003
SA_EVENT_TYPE = 'type="a-f-G-U-C'
PD_EVENT_TYPE = 'parent_callsign='
CONFIG_FILE = 'C:/MSC/MessageCreator64/messagecreator.ini'

# Create the GUI main window
app = Tk()
app.title('WinTAK to Message Machine Adapter - v' + str(APP_VERSION))

# Address Frame
AddressingFrame = LabelFrame(app, text="Addressing & Conditions", padx=5, pady=5)
AddressingFrame.grid(row=0, column=0, padx=5, pady=5)  # Set the frame position

# Messaging Frame
MessagingFrame = LabelFrame(app, text="Status & Messaging", padx=5, pady=5)
MessagingFrame.grid(row=0, column=1, padx=5, pady=5)  # Set the frame position


# Global variables
addressBook = ""
addressBookDataFrame = pd.DataFrame()
addressList = [""]
precedenceList = ["Routine", "Priority", "Immediate", "Training"]
classificationList = ["Unclassified", "Unclassified SVC", "Encrypt For Transmission Only"]
messageSatusList = ["WAITING FOR MESSAGE", "READY TO SEND", "SENDING MESSAGE", "MESSAGE SENT"]
started = True

msgSerial_var = IntVar()
msgSerial_var.set(0)

fromAddress_var = StringVar()
fromAddress_var.set("")

toAddress_var = StringVar()
toAddress_var.set("")

precedence_var = StringVar()
precedence_var.set("")

classification_var = StringVar()
classification_var.set("")

myPosition_var = StringVar()
myPosition_var.set("")

pntDropper_var = StringVar()
pntDropper_var.set("")

# Create the XML document used by message machine
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
positionId.text = 'MessageCreator'
command.text = 'data'
compress.text = '1' # 0 = no compress, 1 = compress
encrypt.text = '1' # 0 = no encrypt, 1 = encrypt
encryptionKey.text = 'MMM'
destinationStation.text = 'ALL'
checksum.text = 'PASS'


# Global functions to show information, warning, and error messages
def showInfo(message):
    response = messagebox.showinfo("Status", message)
    return response

def showWarning(message):
    response = messagebox.showwarning("Warning", message)
    return response

def showError(message):
    response = messagebox.showerror("Error", message)
    return response


# Read the Message Creator configuration file
config = configparser.ConfigParser()
configfile_status = config.read(CONFIG_FILE)
if configfile_status == []:
    showWarning("Message Creator configuration file not found, using default values.")
else:
    try:
        # Read the configuration file and set the inistal value for msgSerial
        msgSerial_var.set(int(config['Station']['msgSerial']))
    except Exception as e:
        showError(e)


# This function is called when the user clicks the "Select an Address Book" button
# It populates the address list and updates the dropdown menus
def selectAddressBook():
    global addressBook, addressBookDataFrame
    try:
        addressBook = filedialog.askopenfilename(initialdir=".", title="Select a MARS Address Book", filetypes=(("csv files", "*.csv"), ("all files", "*.*")))
        addressBook_entry.delete(0, END)
        addressBook_entry.insert(0, addressBook.split("/")[-1])
        createAddressList()
        updateFromAddress()
        updateToAddress()
        addressBookDataFrame = pd.read_csv(addressBook)
        return True
    except Exception as e:
        showError(e)
        return False


# This function is called when the user selects an address book file
# It creates a list of addresses from the address book file
def createAddressList():
    global addressList
    if addressBook_entry.get() == "":
        showWarning("Please select an address book file.")
        return False
    addressList = [""]
    try:
        MARS_AB = pd.read_csv(addressBook_entry.get())
        addressList = MARS_AB['CALL SIGN'].tolist()
        addressList = list(dict.fromkeys(addressList))  # Remove duplicates
        return True
    except Exception as e:
        showError(e)
        return False


# This function is called when the user selects an address book file
# It populates the "From" dropdown menu with the addresses from the address book
def updateFromAddress():
    fromAddress_dropdown['menu'].delete(0, 'end')
    try:
        for address in addressList:
            fromAddress_dropdown['menu'].add_command(label=address, command=lambda value=address: fromAddress_var.set(value))
        return True
    except Exception as e:
        showError(e)
        return False


# This function is called when the user selects an address book file
# It populates the "To" dropdown menu with the addresses from the address book
def updateToAddress():
    toAddress_dropdown['menu'].delete(0, 'end')
    try:
        for address in addressList:
            toAddress_dropdown['menu'].add_command(label=address, command=lambda value=address: toAddress_var.set(value))
        return True
    except Exception as e:
        showError(e)
        return False


# This function is called from sendToMsgMachine()
# This function sets the priority text based on the selected precedence
# and returns the tag for the message
def setPriorityTextAndGetMsgTag():
    global priority
    if precedence_var.get() == "Routine":
        priority.text = '4'
        tag = 'R'
    elif precedence_var.get() == "Priority":
        priority.text = '3'
        tag = 'P'
    elif precedence_var.get() == "Immediate":
        priority.text = '2'
        tag = 'O'
    else:
        priority.text = '4'
        tag = 'R'
    return tag


# This function is called from sendToMsgMachine()
# This function returns a security and classifier based on the selected classification
def getSecurityAndClassification():
    if classification_var.get() == "Unclassified":
        security = 'ZNR UUUUU'
        classifier = 'UNCLAS'
    elif classification_var.get() == "Unclassified SVC":
        security = 'ZNY UUUUU'
        classifier = 'UNCLAS SVC'
    elif classification_var.get() == "Encrypt For Transmission Only":
        security = 'ZNY EEEEE'
        classifier = 'UNCLAS EFTO'
    else:
        security = 'ZNR UUUUU'
        classifier = 'UNCLAS'
    return (security, classifier)


# This function sets the specifieed message status
def setStatus(message_type, status_index):
    if message_type == "position":
        myPositionStatus_entry.delete(0, END)
        myPositionStatus_entry.insert(0, messageSatusList[status_index])
    elif message_type == "point":
        pointDropStatus_entry.delete(0, END)
        pointDropStatus_entry.insert(0, messageSatusList[status_index])
    else:
        # Set the status to "WAITING FOR MESSAGE" for both
        myPositionStatus_entry.delete(0, END)
        myPositionStatus_entry.insert(0, messageSatusList[0])
        pointDropStatus_entry.delete(0, END)
        pointDropStatus_entry.insert(0, messageSatusList[0])


# This function deletes existing CoT messages and sets status to "WAITING FOR MESSAGE"
def cleanup():
    global myPosition_var, pntDropper_var
    try:
        # Set the status to "WAITING FOR MESSAGE"
        setStatus("both", 0)
        # Clear the position and point dropper variables
        myPosition_var.set("")
        pntDropper_var.set("")
        return True
    except Exception as e:
        showError(e)
        return False


# This function is called when the user clicks the "Send to Message Machine" button
# It populates the XML document and sends it in a tcp packet to message machine
def sendToMsgMachine(message_type):
    global sourceStation, destinationStation, data
    try:
        # Check for from and to address
        if fromAddress_var.get() == "" or toAddress_var.get() == "":
            showWarning("Please select a 'From' and 'To' address.")
            return False

        # Check if a position message is ready to send
        if message_type == "position":
            if myPositionStatus_entry.get() == messageSatusList[1]:
                message = myPosition_var.get()
            else:
                showWarning("No position message to send.")
                return False

        # Check if a point drop message is ready to send
        if message_type == "point":
            if pointDropStatus_entry.get() == messageSatusList[1]:
                message = pntDropper_var.get()
            else:
                showWarning("No point drop message to send.")
                return False

        # Set status to "SENDING MESSAGE"
        setStatus(message_type, 2)
        # Fill in the XML header fields
        tag = setPriorityTextAndGetMsgTag()
        sourceStation.text = fromAddress_var.get()
        # Get some information needed for the message header
        security, classifier = getSecurityAndClassification()
        src_routing_indicator = addressBookDataFrame.loc[addressBookDataFrame['CALL SIGN'] == fromAddress_var.get()]['RI'].tolist()[0]
        dst_routing_indicator = addressBookDataFrame.loc[addressBookDataFrame['CALL SIGN'] == toAddress_var.get()]['RI'].tolist()[0]
        src_plaintextAddress = addressBookDataFrame.loc[addressBookDataFrame['CALL SIGN'] == fromAddress_var.get()]['PLA'].tolist()[0]
        dst_plaintextAddress = addressBookDataFrame.loc[addressBookDataFrame['CALL SIGN'] == toAddress_var.get()]['PLA'].tolist()[0]
        date = datetime.now(timezone.utc)
        doy = date.timetuple().tm_yday
        curr_time = date.strftime("%H%M")
        date_time = date.strftime("%d%H%M")
        month = date.strftime("%b").upper()
        year = date.strftime("%Y")
        digest = hashlib.md5(bytes(message,'utf-8')).hexdigest()

        # Fill in the data fields
        data.text = '\nVZCZC' + encryptionKey.text + '999\n'
        data.text += tag + tag + ' ' + dst_routing_indicator + '\n'
        data.text += 'DE ' + src_routing_indicator + ' #' + str(msgSerial_var.get()).zfill(4) + ' ' + str(doy).zfill(3) + curr_time + '\n'
        data.text += security + '\n'
        data.text += tag + ' ' + date_time + 'Z ' + month + ' ' + year + '\n'
        data.text += 'FM ' + src_plaintextAddress + '\n'
        data.text += 'TO ' + dst_routing_indicator + '/' + dst_plaintextAddress + '\n'
        data.text += 'BT\n'
        data.text += classifier + '\n'
        data.text += message + '\n'
        data.text += 'BT\n'
        data.text += '#' + str(msgSerial_var.get()).zfill(4) + '\n'
        data.text += '[DIGEST:' + digest.upper() + ']\n'
        if precedence_var.get() == "Training":
            data.text += 'TRAINING MESSAGE TAKE NO ACTION\n'
        data.text += '\nNNNN\n'

        # Create a byte array from the XML document
        xml_string = ET.tostring(v3protocol, encoding='utf8', method='xml', xml_declaration=True) + b'\n'
        
        # Write the XML string to a file for debugging purposes
        #with open("test.xml", "wb") as f:
        #    f.write(xml_string)

        # Send the XML string to message machine via TCP socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((LOCALHOST, MSG_MACHINE_PORT))
            response = s.recv(1024)
            time.sleep(1)  # Sleep for 1 second
            s.sendall(xml_string)
            # Set status to "MESSAGE SENT"
            setStatus(message_type, 3)
            time.sleep(1)  # Sleep for 1 second

        msgSerial_var.set(msgSerial_var.get() + 1)  # Increment the message serial number
        return True

    except Exception as e:
        cleanup()
        showError(e)
        return False


# Create GUI elements within the AddressingFrame
addressBook_button = Button(AddressingFrame, text="Select an Address Book", width=24, command=selectAddressBook)  # Create a button
addressBook_button.grid(row=0, column=0, padx=5, pady=0)
addressBook_entry = Entry(AddressingFrame, width=18, borderwidth=5)  # Create an entry widget
addressBook_entry.grid(row=0, column=1, padx=0, pady=0)  # Put the entry into the window

toAddress_label = Label(AddressingFrame, width=24, anchor="e", text="Select Callsign To:")  # Create a label widget
toAddress_label.grid(row=1, column=0, padx=0, pady=0)  # Put the label into the window
toAddress_dropdown = OptionMenu(AddressingFrame, toAddress_var, *addressList)
toAddress_dropdown.grid(row=1, column=1, sticky="w", padx=0, pady=0)

fromAddress_label = Label(AddressingFrame, width=24, anchor="e", text="Select Callsign From:")  # Create a label widget
fromAddress_label.grid(row=2, column=0, padx=0, pady=0)  # Put the label into the window
fromAddress_dropdown = OptionMenu(AddressingFrame, fromAddress_var, *addressList)
fromAddress_dropdown.grid(row=2, column=1, sticky="w", padx=0, pady=0)

precedence_label = Label(AddressingFrame, width=24, anchor="e", text="Select Precedence:")  # Create a label widget
precedence_label.grid(row=3, column=0, padx=0, pady=0)  # Put the label into the window
precedence_dropdown = OptionMenu(AddressingFrame, precedence_var, *precedenceList)
precedence_dropdown.grid(row=3, column=1, sticky="w", padx=0, pady=0)

classification_label = Label(AddressingFrame, width=24, anchor="e", text="Select Classification:")  # Create a label widget
classification_label.grid(row=4, column=0, padx=0, pady=0)  # Put the label into the window
classification_dropdown = OptionMenu(AddressingFrame, classification_var, *classificationList)
classification_dropdown.grid(row=4, column=1, sticky="w", padx=0, pady=0)

# Create GUI elements within the MessagingFrame
myPositionStatus_label = Label(MessagingFrame, width=18, anchor="e", text="Position Status:")  # Create a label widget
myPositionStatus_label.grid(row=0, column=0, padx=5, pady=5)  # Put the label into the window
myPositionStatus_entry = Entry(MessagingFrame, width=32, borderwidth=0)  # Create an entry widget
myPositionStatus_entry.grid(row=0, column=1, padx=0, pady=5)  # Put the entry into the window

sendSAMessageButton = Button(MessagingFrame, text="Send My Position to MessageMachine", width=47, command=lambda: sendToMsgMachine("position"))  # Create a button
sendSAMessageButton.grid(row=1, column=0, columnspan=2, padx=5, pady=9)

pointDropStatus_label = Label(MessagingFrame, width=18, anchor="e", text="Point Dropper Status:")  # Create a label widget
pointDropStatus_label.grid(row=2, column=0, padx=5, pady=5)  # Put the label into the window
pointDropStatus_entry = Entry(MessagingFrame, width=32, borderwidth=0)  # Create an entry widget
pointDropStatus_entry.grid(row=2, column=1, padx=0, pady=5)  # Put the entry into the window

sendPDMessageButton = Button(MessagingFrame, text="Send Point Dropper to MessageMachine", width=47, command=lambda: sendToMsgMachine("point"))  # Create a button
sendPDMessageButton.grid(row=3, column=0, columnspan=2, padx=5, pady=9)


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
    try:
        # Create a UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(1.0)
        # Allow multiple sockets to use the same port number
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind the socket to the port
        sock.bind((LOCALHOST, COTXML_PORT))
    except socket.error as e:
        showError(f"Socket error: {e}")
        return False

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
            if is_pd_event(xml[1]):
                pntDropper_var.set(xml[1])
                setStatus("point", 1)
            elif is_sa_event(xml[1]):
                myPosition_var.set(xml[1])
                setStatus("position", 1)
        except socket.timeout:
            continue

    print("Exiting CoT XML Listener thread...")
    # Close the udp socket
    try:
        sock.close()
        return True
    except Exception as e:
        showError(e)
        return False


# Initialize the message status entry fields
setStatus("both", 0)
# Start the CoT XML Listener thread
cotXmlThread = threading.Thread(target=cotXmlListener, args=(1,))
cotXmlThread.start()


def app_exit():

    close = messagebox.askyesno("Exit?", "Are you sure you want to exit the application?")
    if close:
        global started, configfile_status
        started = False  # Stop the loop in the cotXmlListener thread
        # Save our changes to msgSerial to the Message Creator configuration file
        if configfile_status != []:
            try:
                # Write the current msgSerial value to the configuration file
                config['Station']['msgSerial'] = str(msgSerial_var.get())
                with open(CONFIG_FILE, 'w') as configfile:
                    config.write(configfile)
            except Exception as e:
                showError(e)

        time.sleep(2)  # Sleep for 2 seconds to allow the thread to finish
        app.destroy()

app.protocol("WM_DELETE_WINDOW", app_exit)

app.mainloop()  # Keep the window open
