#include "common.h"

#include <errno.h>
#include <sys/socket.h>

uint64_t MultModulo(uint64_t a, uint64_t b, uint64_t mod) {
  uint64_t result = 0;
  a %= mod;
  while (b > 0) {
    if (b % 2 != 0)
      result = (result >= mod - a) ? result - (mod - a) : result + a;
    a = (a >= mod - a) ? a - (mod - a) : a + a;
    b /= 2;
  }
  return result;
}

bool SendAll(int fd, const void *data, size_t size) {
  const char *bytes = data;
  size_t sent = 0;
  while (sent < size) {
    ssize_t n = send(fd, bytes + sent, size - sent, MSG_NOSIGNAL);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0)
      return false;
    sent += (size_t)n;
  }
  return true;
}

bool RecvAll(int fd, void *data, size_t size) {
  char *bytes = data;
  size_t received = 0;
  while (received < size) {
    ssize_t n = recv(fd, bytes + received, size - received, 0);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0)
      return false;
    received += (size_t)n;
  }
  return true;
}
