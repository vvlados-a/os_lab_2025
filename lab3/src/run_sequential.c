#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc != 3) {
    printf("Usage: %s seed arraysize\n", argv[0]);
    return 1;
  }

  pid_t child_pid = fork();
  if (child_pid == -1) {
    perror("fork");
    return 1;
  }

  if (child_pid == 0) {
    execl("./sequential_min_max", "sequential_min_max", argv[1], argv[2],
          (char *)NULL);

    perror("execl");
    _exit(1);
  }

  int status = 0;
  if (waitpid(child_pid, &status, 0) == -1) {
    perror("waitpid");
    return 1;
  }

  if (!WIFEXITED(status)) {
    fprintf(stderr, "sequential_min_max terminated abnormally\n");
    return 1;
  }

  return WEXITSTATUS(status);
}
