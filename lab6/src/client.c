#include <arpa/inet.h>
#include <errno.h>
#include <getopt.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "common.h"

struct Server {
  char ip[255];
  int port;
};

struct ServerTask {
  struct Server server;
  uint64_t begin;
  uint64_t end;
  uint64_t mod;
  uint64_t result;
  bool success;
};

static bool ParseU64(const char *str, uint64_t *value) {
  if (*str == '\0' || *str == '-' || *str == '+')
    return false;
  errno = 0;
  char *end = NULL;
  unsigned long long number = strtoull(str, &end, 10);
  if (errno != 0 || *end != '\0')
    return false;
  *value = (uint64_t)number;
  return true;
}

static bool ReadServers(const char *path, struct Server **servers,
                        size_t *count) {
  FILE *file = fopen(path, "r");
  if (!file) {
    perror(path);
    return false;
  }

  char line[512];
  *servers = NULL;
  *count = 0;
  while (fgets(line, sizeof(line), file)) {
    size_t len = strlen(line);
    if (len == sizeof(line) - 1 && line[len - 1] != '\n' && !feof(file)) {
      fprintf(stderr, "Server address is too long\n");
      goto error;
    }
    line[strcspn(line, "\r\n")] = '\0';
    if (line[0] == '\0')
      continue;

    char *colon = strrchr(line, ':');
    if (!colon || colon == line || strlen(line) >= sizeof((*servers)[0].ip) + 6) {
      fprintf(stderr, "Invalid server address: %s\n", line);
      goto error;
    }
    *colon = '\0';
    if (strlen(line) >= sizeof((*servers)[0].ip)) {
      fprintf(stderr, "IP address is too long\n");
      goto error;
    }
    uint64_t port;
    if (!ParseU64(colon + 1, &port) || port < 1 || port > 65535) {
      fprintf(stderr, "Invalid server port: %s\n", colon + 1);
      goto error;
    }

    struct Server *new_servers = realloc(*servers, (*count + 1) * sizeof(**servers));
    if (!new_servers) {
      perror("realloc");
      goto error;
    }
    *servers = new_servers;
    strcpy((*servers)[*count].ip, line);
    (*servers)[*count].port = (int)port;
    ++*count;
  }
  if (ferror(file) || *count == 0) {
    fprintf(stderr, "Could not read any servers\n");
    goto error;
  }
  fclose(file);
  return true;

error:
  free(*servers);
  *servers = NULL;
  *count = 0;
  fclose(file);
  return false;
}

static void *RunServer(void *argument) {
  struct ServerTask *task = argument;
  struct sockaddr_in address = {0};
  address.sin_family = AF_INET;
  address.sin_port = htons((uint16_t)task->server.port);
  if (inet_pton(AF_INET, task->server.ip, &address.sin_addr) != 1) {
    fprintf(stderr, "Invalid IPv4 address: %s\n", task->server.ip);
    return NULL;
  }

  int fd = socket(AF_INET, SOCK_STREAM, 0);
  if (fd < 0) {
    perror("socket");
    return NULL;
  }
  if (connect(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
    perror("connect");
    close(fd);
    return NULL;
  }

  // Same three uint64_t fields as in the original teacher's client/server.
  uint64_t request[3] = {task->begin, task->end, task->mod};
  if (!SendAll(fd, request, sizeof(request)) ||
      !RecvAll(fd, &task->result, sizeof(task->result))) {
    fprintf(stderr, "Network exchange failed: %s:%d\n", task->server.ip,
            task->server.port);
    close(fd);
    return NULL;
  }
  task->success = true;
  close(fd);
  return NULL;
}

int main(int argc, char **argv) {
  uint64_t k = 0, mod = 0;
  bool have_k = false, have_mod = false;
  const char *servers_path = NULL;
  static struct option options[] = {
      {"k", required_argument, NULL, 'k'},
      {"mod", required_argument, NULL, 'm'},
      {"servers", required_argument, NULL, 's'},
      {0, 0, 0, 0}};

  int option;
  while ((option = getopt_long(argc, argv, "", options, NULL)) != -1) {
    switch (option) {
    case 'k':
      have_k = ParseU64(optarg, &k);
      break;
    case 'm':
      have_mod = ParseU64(optarg, &mod);
      break;
    case 's':
      servers_path = optarg;
      break;
    default:
      return 1;
    }
  }
  if (!have_k || !have_mod || mod == 0 || !servers_path || optind != argc) {
    fprintf(stderr, "Usage: %s --k 20 --mod 1000000007 --servers servers.txt\n",
            argv[0]);
    return 1;
  }

  struct Server *servers = NULL;
  size_t count = 0;
  if (!ReadServers(servers_path, &servers, &count))
    return 1;

  pthread_t *threads = calloc(count, sizeof(*threads));
  struct ServerTask *tasks = calloc(count, sizeof(*tasks));
  if (!threads || !tasks) {
    perror("calloc");
    free(threads);
    free(tasks);
    free(servers);
    return 1;
  }

  uint64_t base = k / count;
  uint64_t extra = k % count;
  uint64_t begin = 1;
  size_t created = 0;
  for (size_t i = 0; i < count; ++i) {
    uint64_t length = base + (i < extra);
    tasks[i].server = servers[i];
    tasks[i].begin = begin;
    tasks[i].end = length ? begin + length - 1 : begin - 1;
    tasks[i].mod = mod;
    if (i + 1 < count && length)
      begin = tasks[i].end + 1;

    int err = pthread_create(&threads[i], NULL, RunServer, &tasks[i]);
    if (err != 0) {
      fprintf(stderr, "pthread_create failed: %s\n", strerror(err));
      break;
    }
    ++created;
  }

  uint64_t answer = 1 % mod;
  bool success = (created == count);
  for (size_t i = 0; i < created; ++i) {
    pthread_join(threads[i], NULL);
    if (!tasks[i].success) {
      success = false;
      continue;
    }
    printf("%s:%d [%llu, %llu] -> %llu\n", tasks[i].server.ip,
           tasks[i].server.port, (unsigned long long)tasks[i].begin,
           (unsigned long long)tasks[i].end,
           (unsigned long long)tasks[i].result);
    answer = MultModulo(answer, tasks[i].result, mod);
  }

  if (success)
    printf("answer: %llu\n", (unsigned long long)answer);
  else
    fprintf(stderr, "Could not calculate the result\n");

  free(tasks);
  free(threads);
  free(servers);
  return success ? 0 : 1;
}
