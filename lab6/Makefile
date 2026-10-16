CC = gcc
CFLAGS = -std=c11 -Wall -Wextra -Wpedantic -O2 -pthread

all: client server

client: src/client.o libcommon.a
	$(CC) $(CFLAGS) -o $@ src/client.o libcommon.a

server: src/server.o libcommon.a
	$(CC) $(CFLAGS) -o $@ src/server.o libcommon.a

libcommon.a: src/common.o
	ar rcs $@ $^

src/%.o: src/%.c src/common.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f client server src/*.o libcommon.a

.PHONY: all clean
