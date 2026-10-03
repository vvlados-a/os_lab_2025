/* Program to display address information about the process. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern char etext, edata, end;

#define SHOW_OBJECT_ADDRESS(ID, OBJECT)                                        \
  printf("ID %-8s is at virtual address: %p\n", ID, (void *)&(OBJECT))

const char *cptr = "This message is output by the function showit()\n";
char buffer1[25];

static void showit(const char *p);

int main(void) {
  int i = 0;

  printf("Address etext: %p\n", (void *)&etext);
  printf("Address edata: %p\n", (void *)&edata);
  printf("Address end  : %p\n", (void *)&end);

  printf("ID %-8s is at virtual address: %p\n", "main",
         (void *)(uintptr_t)&main);
  printf("ID %-8s is at virtual address: %p\n", "showit",
         (void *)(uintptr_t)&showit);
  SHOW_OBJECT_ADDRESS("cptr", cptr);
  SHOW_OBJECT_ADDRESS("buffer1", buffer1);
  SHOW_OBJECT_ADDRESS("i", i);

  strcpy(buffer1, "A demonstration\n");
  fflush(stdout);
  if (write(STDOUT_FILENO, buffer1, strlen(buffer1)) == -1) {
    perror("write");
    return 1;
  }

  showit(cptr);
  return 0;
}

static void showit(const char *p) {
  char *buffer2;
  SHOW_OBJECT_ADDRESS("buffer2", buffer2);

  buffer2 = malloc(strlen(p) + 1);
  if (buffer2 == NULL) {
    perror("malloc");
    exit(1);
  }

  printf("Allocated memory at %p\n", (void *)buffer2);
  strcpy(buffer2, p);
  printf("%s", buffer2);
  free(buffer2);
}
