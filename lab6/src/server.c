#include <errno.h>
#include <getopt.h>
#include <limits.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "common.h"

struct FactorialArgs {
  uint64_t begin;
  uint64_t end;
  uint64_t mod;
  uint64_t result;
};

static uint64_t Factorial(const struct FactorialArgs *args) {
  uint64_t answer = 1 % args->mod;
  if (args->begin > args->end)
    return answer;
  for (uint64_t i = args->begin;; ++i) {
    answer = MultModulo(answer, i, args->mod);
    if (i == args->end)
      break;
  }
  return answer;
}

static void *ThreadFactorial(void *argument) {
  struct FactorialArgs *args = argument;
  args->result = Factorial(args);
  return NULL;
}

static bool ParsePositiveInt(const char *str, int max, int *value) {
  if (!*str)
    return false;
  errno = 0;
  char *end = NULL;
  long number = strtol(str, &end, 10);
  if (errno != 0 || *end || number < 1 || number > max)
    return false;
  *value = (int)number;
  return true;
}

static bool Calculate(uint64_t begin, uint64_t end, uint64_t mod,
                      int tnum, uint64_t *total) {
  uint64_t length = begin <= end ? end - begin + 1 : 0;
  size_t count = length < (uint64_t)tnum ? (size_t)length : (size_t)tnum;
  *total = 1 % mod;
  if (count == 0)
    return true;

  pthread_t *threads = calloc(count, sizeof(*threads));
  struct FactorialArgs *args = calloc(count, sizeof(*args));
  if (!threads || !args) {
    free(threads);
    free(args);
    return false;
  }

  uint64_t base = length / count;
  uint64_t extra = length % count;
  uint64_t current = begin;
  size_t created = 0;
  for (size_t i = 0; i < count; ++i) {
    uint64_t size = base + (i < extra);
    args[i].begin = current;
    args[i].end = current + size - 1;
    args[i].mod = mod;
    if (i + 1 < count)
      current = args[i].end + 1;

    int err = pthread_create(&threads[i], NULL, ThreadFactorial, &args[i]);
    if (err != 0) {
      fprintf(stderr, "pthread_create failed: %s\n", strerror(err));
      break;
    }
    ++created;
  }

  bool success = (created == count);
  for (size_t i = 0; i < created; ++i) {
    pthread_join(threads[i], NULL);
    *total = MultModulo(*total, args[i].result, mod);
  }
  free(args);
  free(threads);
  return success;
}

int main(int argc, char **argv) {
  int port = 0, tnum = 0;
  static struct option options[] = {
      {"port", required_argument, NULL, 'p'},
      {"tnum", required_argument, NULL, 't'},
      {0, 0, 0, 0}};

  int option;
  while ((option = getopt_long(argc, argv, "", options, NULL)) != -1) {
    switch (option) {
    case 'p':
      if (!ParsePositiveInt(optarg, 65535, &port)) {
        fprintf(stderr, "Invalid port\n");
        return 1;
      }
      break;
    case 't':
      if (!ParsePositiveInt(optarg, INT_MAX, &tnum)) {
        fprintf(stderr, "Invalid thread count\n");
        return 1;
      }
      break;
    default:
      return 1;
    }
  }
  if (port == 0 || tnum == 0 || optind != argc) {
    fprintf(stderr, "Usage: %s --port 20001 --tnum 4\n", argv[0]);
    return 1;
  }

  int server_fd = socket(AF_INET, SOCK_STREAM, 0);
  if (server_fd < 0) {
    perror("socket");
    return 1;
  }
  int reuse = 1;
  setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

  struct sockaddr_in server = {0};
  server.sin_family = AF_INET;
  server.sin_port = htons((uint16_t)port);
  server.sin_addr.s_addr = htonl(INADDR_ANY);
  if (bind(server_fd, (struct sockaddr *)&server, sizeof(server)) < 0 ||
      listen(server_fd, 128) < 0) {
    perror("bind/listen");
    close(server_fd);
    return 1;
  }
  printf("Server listening at %d (threads: %d)\n", port, tnum);
  fflush(stdout);

  while (true) {
    int client_fd = accept(server_fd, NULL, NULL);
    if (client_fd < 0) {
      if (errno != EINTR)
        perror("accept");
      continue;
    }

    uint64_t request[3];
    if (RecvAll(client_fd, request, sizeof(request)) && request[2] != 0) {
      uint64_t total;
      printf("Received [%llu, %llu], mod %llu\n",
             (unsigned long long)request[0], (unsigned long long)request[1],
             (unsigned long long)request[2]);
      if (Calculate(request[0], request[1], request[2], tnum, &total)) {
        printf("Total: %llu\n", (unsigned long long)total);
        if (!SendAll(client_fd, &total, sizeof(total)))
          perror("send");
      } else {
        fprintf(stderr, "Calculation failed\n");
      }
      fflush(stdout);
    } else {
      fprintf(stderr, "Invalid or incomplete request\n");
    }
    close(client_fd);
  }
}
