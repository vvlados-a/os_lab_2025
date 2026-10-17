#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
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

  char *sendline = malloc((size_t)size);
  char *recvline = malloc((size_t)size);
  if (sendline == NULL || recvline == NULL) {
    perror("malloc");
    free(sendline);
    free(recvline);
    return 1;
  }

  struct sockaddr_in servaddr = {0};
  servaddr.sin_family = AF_INET;
  servaddr.sin_port = htons((unsigned short)port);
  if (inet_pton(AF_INET, argv[1], &servaddr.sin_addr) != 1) {
    fprintf(stderr, "Invalid server IP address\n");
    free(sendline);
    free(recvline);
    return 1;
  }

  int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
  if (sockfd < 0) {
    perror("socket");
    free(sendline);
    free(recvline);
    return 1;
  }

  printf("Enter string\n");
  fflush(stdout);

  ssize_t n;
  while ((n = read(STDIN_FILENO, sendline, (size_t)size)) > 0) {
    if (sendto(sockfd, sendline, (size_t)n, 0,
               (struct sockaddr *)&servaddr, sizeof(servaddr)) < 0) {
      perror("sendto");
      close(sockfd);
      free(sendline);
      free(recvline);
      return 1;
    }

    ssize_t received = recvfrom(sockfd, recvline, (size_t)size, 0, NULL, NULL);
    if (received < 0) {
      perror("recvfrom");
      close(sockfd);
      free(sendline);
      free(recvline);
      return 1;
    }
    printf("REPLY FROM SERVER= ");
    fwrite(recvline, 1, (size_t)received, stdout);
    if (received == 0 || recvline[received - 1] != '\n') {
      putchar('\n');
    }
    fflush(stdout);
  }
  if (n < 0) {
    perror("read");
    close(sockfd);
    free(sendline);
    free(recvline);
    return 1;
  }

  close(sockfd);
  free(sendline);
  free(recvline);
  return 0;
}
