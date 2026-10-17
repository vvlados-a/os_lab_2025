CC = gcc
CFLAGS = -std=c11 -Wall -Wextra

all: tcpclient tcpserver udpclient udpserver

tcpclient: tcpclient.c
	$(CC) $(CFLAGS) tcpclient.c -o tcpclient

tcpserver: tcpserver.c
	$(CC) $(CFLAGS) tcpserver.c -o tcpserver

udpclient: udpclient.c
	$(CC) $(CFLAGS) udpclient.c -o udpclient

udpserver: udpserver.c
	$(CC) $(CFLAGS) udpserver.c -o udpserver

clean:
	rm -f tcpclient tcpserver udpclient udpserver

.PHONY: all clean
