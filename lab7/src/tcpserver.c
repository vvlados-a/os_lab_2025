#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
  if (argc != 3) {
    fprintf(stderr, "Usage: %s <port> <buffer_size>\n", argv[0]);
    return 1;
  }

  char *end;
  errno = 0;
  long port = strtol(argv[1], &end, 10);
  if (errno != 0 || end == argv[1] || *end != '\0' || port < 1 || port > 65535) {
    fprintf(stderr, "Invalid port\n");
    return 1;
  }

  errno = 0;
  long size = strtol(argv[2], &end, 10);
  if (errno != 0 || end == argv[2] || *end != '\0' || size <= 0) {
    fprintf(stderr, "Invalid buffer size\n");
    return 1;
  }

  char *buf = malloc((size_t)size);
  if (buf == NULL) {
    perror("malloc");
    return 1;
  }

  int lfd = socket(AF_INET, SOCK_STREAM, 0);
  if (lfd < 0) {
    perror("socket");
    free(buf);
    return 1;
  }

  struct sockaddr_in servaddr = {0};
  servaddr.sin_family = AF_INET;
  servaddr.sin_addr.s_addr = htonl(INADDR_ANY);
  servaddr.sin_port = htons((unsigned short)port);

  if (bind(lfd, (struct sockaddr *)&servaddr, sizeof(servaddr)) < 0) {
    perror("bind");
    close(lfd);
    free(buf);
    return 1;
  }
  if (listen(lfd, 5) < 0) {
    perror("listen");
    close(lfd);
    free(buf);
    return 1;
  }

  while (1) {
    struct sockaddr_in cliaddr;
    socklen_t clilen = sizeof(cliaddr);
    int cfd = accept(lfd, (struct sockaddr *)&cliaddr, &clilen);
    if (cfd < 0) {
      perror("accept");
      close(lfd);
      free(buf);
      return 1;
    }
    printf("connection established\n");
    fflush(stdout);

    ssize_t nread;
    while ((nread = read(cfd, buf, (size_t)size)) > 0) {
      if (fwrite(buf, 1, (size_t)nread, stdout) != (size_t)nread) {
        perror("fwrite");
        close(cfd);
        close(lfd);
        free(buf);
        return 1;
      }
      fflush(stdout);
    }
    if (nread < 0) {
      perror("read");
    }
    close(cfd);
  }
}
