CC=gcc
CFLAGS=-I. -Wall -Wextra -Wpedantic

.PHONY: all clean

all: sequential_min_max parallel_min_max run_sequential

sequential_min_max: sequential_min_max.c utils.o find_min_max.o utils.h find_min_max.h
	$(CC) -o sequential_min_max find_min_max.o utils.o sequential_min_max.c $(CFLAGS)

parallel_min_max: parallel_min_max.c utils.o find_min_max.o utils.h find_min_max.h
	$(CC) -o parallel_min_max utils.o find_min_max.o parallel_min_max.c $(CFLAGS)

run_sequential: run_sequential.c sequential_min_max
	$(CC) -o run_sequential run_sequential.c $(CFLAGS)

utils.o: utils.c utils.h
	$(CC) -o utils.o -c utils.c $(CFLAGS)

find_min_max.o: find_min_max.c utils.h find_min_max.h
	$(CC) -o find_min_max.o -c find_min_max.c $(CFLAGS)

clean:
	rm -f utils.o find_min_max.o sequential_min_max parallel_min_max run_sequential min_max_*.tmp
