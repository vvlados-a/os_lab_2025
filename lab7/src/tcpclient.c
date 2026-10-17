#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
  if (argc != 4) {
    fprintf(stderr, "Usage: %s <server_ip> <port> <buffer_size>\n", argv[0]);
    return 1;
  }

  char *end;
  errno = 0;
  long port = strtol(argv[2], &end, 10);
  if (errno != 0 || end == argv[2] || *end != '\0' || port < 1 || port > 65535) {
    fprintf(stderr, "Invalid port\n");
    return 1;
  }

  errno = 0;
  long size = strtol(argv[3], &end, 10);
  if (errno != 0 || end == argv[3] || *end != '\0' || size <= 0) {
    fprintf(stderr, "Invalid buffer size\n");
    return 1;
  }

  char *buf = malloc((size_t)size);
  if (buf == NULL) {
    perror("malloc");
    return 1;
  }

  struct sockaddr_in servaddr = {0};
  servaddr.sin_family = AF_INET;
  servaddr.sin_port = htons((unsigned short)port);
  if (inet_pton(AF_INET, argv[1], &servaddr.sin_addr) != 1) {
    fprintf(stderr, "Invalid server IP address\n");
    free(buf);
    return 1;
  }

  int fd = socket(AF_INET, SOCK_STREAM, 0);
  if (fd < 0) {
    perror("socket");
    free(buf);
    return 1;
  }
  if (connect(fd, (struct sockaddr *)&servaddr, sizeof(servaddr)) < 0) {
    perror("connect");
    close(fd);
    free(buf);
    return 1;
  }

  printf("Input message to send\n");
  fflush(stdout);

  ssize_t nread;
  while ((nread = read(STDIN_FILENO, buf, (size_t)size)) > 0) {
    ssize_t sent = 0;
    while (sent < nread) {
      ssize_t n = write(fd, buf + sent, (size_t)(nread - sent));
      if (n <= 0) {
        perror("write");
        close(fd);
        free(buf);
        return 1;
      }
      sent += n;
    }
  }
  if (nread < 0) {
    perror("read");
    close(fd);
    free(buf);
    return 1;
  }

  close(fd);
  free(buf);
  return 0;
}
