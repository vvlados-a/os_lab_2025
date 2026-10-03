CC = gcc
AR = ar
CPPFLAGS = -I. -D_POSIX_C_SOURCE=200809L
CFLAGS = -std=c11 -Wall -Wextra -Wpedantic
PTHREAD_FLAGS = -pthread

.PHONY: all task4 task6 clean

all: parallel_min_max process_memory zombie psum

# Task 4: programs from tasks 1 and 3.
task4: parallel_min_max process_memory

# Task 6: parallel_sum program.
task6: psum

parallel_min_max: parallel_min_max.c utils.o find_min_max.o utils.h find_min_max.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ parallel_min_max.c utils.o find_min_max.o

process_memory: process_memory.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ process_memory.c

zombie: zombie.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ zombie.c

psum: parallel_sum.c utils.o libsum.a utils.h sum.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(PTHREAD_FLAGS) -o $@ parallel_sum.c utils.o -L. -lsum $(PTHREAD_FLAGS)

libsum.a: sum.o
	$(AR) rcs $@ sum.o

sum.o: sum.c sum.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -c sum.c -o $@

utils.o: utils.c utils.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -c utils.c -o $@

find_min_max.o: find_min_max.c find_min_max.h utils.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -c find_min_max.c -o $@

clean:
	rm -f *.o *.a parallel_min_max process_memory zombie psum min_max_*.tmp
