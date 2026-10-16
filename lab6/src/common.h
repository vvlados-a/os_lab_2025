#ifndef COMMON_H
#define COMMON_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

uint64_t MultModulo(uint64_t a, uint64_t b, uint64_t mod);
bool SendAll(int fd, const void *data, size_t size);
bool RecvAll(int fd, void *data, size_t size);

#endif
