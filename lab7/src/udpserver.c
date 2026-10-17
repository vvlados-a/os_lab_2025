#include <arpa/inet.h>
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

  char *mesg = malloc((size_t)size);
  if (mesg == NULL) {
    perror("malloc");
    return 1;
  }

  int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
  if (sockfd < 0) {
    perror("socket");
    free(mesg);
    return 1;
  }

  struct sockaddr_in servaddr = {0};
  servaddr.sin_family = AF_INET;
  servaddr.sin_addr.s_addr = htonl(INADDR_ANY);
  servaddr.sin_port = htons((unsigned short)port);
  if (bind(sockfd, (struct sockaddr *)&servaddr, sizeof(servaddr)) < 0) {
    perror("bind");
    close(sockfd);
    free(mesg);
    return 1;
  }
  printf("SERVER starts...\n");
  fflush(stdout);

  while (1) {
    struct sockaddr_in cliaddr;
    socklen_t len = sizeof(cliaddr);
    ssize_t n = recvfrom(sockfd, mesg, (size_t)size, 0,
                         (struct sockaddr *)&cliaddr, &len);
    if (n < 0) {
      perror("recvfrom");
      close(sockfd);
      free(mesg);
      return 1;
    }

    char ipadr[INET_ADDRSTRLEN];
    const char *ip = inet_ntop(AF_INET, &cliaddr.sin_addr, ipadr, sizeof(ipadr));
    printf("REQUEST ");
    fwrite(mesg, 1, (size_t)n, stdout);
    printf("      FROM %s : %u\n", ip != NULL ? ip : "?", ntohs(cliaddr.sin_port));
    fflush(stdout);

    if (sendto(sockfd, mesg, (size_t)n, 0,
               (struct sockaddr *)&cliaddr, len) < 0) {
      perror("sendto");
      close(sockfd);
      free(mesg);
      return 1;
    }
  }
}
