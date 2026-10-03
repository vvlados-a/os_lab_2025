#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
  pid_t child_pid = fork();

  if (child_pid == -1) {
    perror("fork");
    return 1;
  }

  if (child_pid == 0) {
    printf("Child: PID=%ld. Exiting now.\n", (long)getpid());
    fflush(stdout);
    _exit(0);
  }

  printf("Parent: PID=%ld, child PID=%ld.\n", (long)getpid(),
         (long)child_pid);
  printf("Parent does not call waitpid() yet, so the terminated child becomes "
         "a zombie.\n\n");
  fflush(stdout);

  sleep(1);

  char command[160];
  snprintf(command, sizeof(command),
           "ps -o pid,ppid,state,stat,cmd -p %ld", (long)child_pid);

  printf("Before waitpid():\n");
  fflush(stdout);
  if (system(command) == -1) {
    perror("system");
  }

  int status = 0;
  if (waitpid(child_pid, &status, 0) == -1) {
    perror("waitpid");
    return 1;
  }

  printf("\nAfter waitpid(): the zombie has been reaped.\n");
  printf("The same ps command now finds no process with PID %ld:\n",
         (long)child_pid);
  fflush(stdout);
  if (system(command) == -1) {
    perror("system");
  }

  return 0;
}
