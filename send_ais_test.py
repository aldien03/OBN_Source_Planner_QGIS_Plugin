import socket

# Define the AIS message
ais_message = '!AIVDM,1,1,,A,15Muq@001o;RrTpE>4@>4?wP0000,0*5C'

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send the AIS message to localhost on port 2000
sock.sendto(ais_message.encode(), ('127.0.0.1', 2000))

# Close the socket
sock.close()
