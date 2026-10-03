#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>

#include <getopt.h>

#include "find_min_max.h"
#include "utils.h"

static void GetResultFileName(char *buffer, size_t buffer_size, pid_t parent_pid,
                              int process_number) {
  snprintf(buffer, buffer_size, "min_max_%ld_%d.tmp", (long)parent_pid,
           process_number);
}

int main(int argc, char **argv) {
  int seed = -1;
  int array_size = -1;
  int pnum = -1;
  bool with_files = false;

  static struct option options[] = {{"seed", required_argument, 0, 0},
                                    {"array_size", required_argument, 0, 0},
                                    {"pnum", required_argument, 0, 0},
                                    {"by_files", no_argument, 0, 'f'},
                                    {0, 0, 0, 0}};

  while (true) {
    int option_index = 0;
    int c = getopt_long(argc, argv, "f", options, &option_index);

    if (c == -1) {
      break;
    }

    switch (c) {
      case 0:
        switch (option_index) {
          case 0:
            seed = atoi(optarg);
            if (seed <= 0) {
              printf("seed is a positive number\n");
              return 1;
            }
            break;
          case 1:
            array_size = atoi(optarg);
            if (array_size <= 0) {
              printf("array_size is a positive number\n");
              return 1;
            }
            break;
          case 2:
            pnum = atoi(optarg);
            if (pnum <= 0) {
              printf("pnum is a positive number\n");
              return 1;
            }
            break;
          default:
            printf("Index %d is out of options\n", option_index);
            return 1;
        }
        break;

      case 'f':
        with_files = true;
        break;

      case '?':
        return 1;

      default:
        printf("getopt returned character code 0%o?\n", c);
        return 1;
    }
  }

  if (optind < argc) {
    printf("Has at least one no option argument\n");
    return 1;
  }

  if (seed == -1 || array_size == -1 || pnum == -1) {
    printf("Usage: %s --seed \"num\" --array_size \"num\" --pnum \"num\" "
           "[--by_files]\n",
           argv[0]);
    return 1;
  }

  int *array = malloc((size_t)array_size * sizeof(int));
  if (array == NULL) {
    perror("malloc array");
    return 1;
  }
  GenerateArray(array, (unsigned int)array_size, (unsigned int)seed);

  pid_t *child_pids = malloc((size_t)pnum * sizeof(pid_t));
  if (child_pids == NULL) {
    perror("malloc child_pids");
    free(array);
    return 1;
  }

  int (*pipes)[2] = NULL;
  if (!with_files) {
    pipes = malloc((size_t)pnum * sizeof(*pipes));
    if (pipes == NULL) {
      perror("malloc pipes");
      free(child_pids);
      free(array);
      return 1;
    }

    for (int i = 0; i < pnum; i++) {
      if (pipe(pipes[i]) == -1) {
        perror("pipe");
        for (int j = 0; j < i; j++) {
          close(pipes[j][0]);
          close(pipes[j][1]);
        }
        free(pipes);
        free(child_pids);
        free(array);
        return 1;
      }
    }
  }

  pid_t parent_pid = getpid();
  int active_child_processes = 0;
  bool fork_failed = false;

  struct timeval start_time;
  gettimeofday(&start_time, NULL);

  for (int i = 0; i < pnum; i++) {
    pid_t child_pid = fork();

    if (child_pid == -1) {
      perror("fork");
      fork_failed = true;
      break;
    }

    if (child_pid == 0) {
      unsigned int begin =
          (unsigned int)(((unsigned long long)i * (unsigned int)array_size) /
                         (unsigned int)pnum);
      unsigned int end =
          (unsigned int)(((unsigned long long)(i + 1) *
                          (unsigned int)array_size) /
                         (unsigned int)pnum);

      struct MinMax local_min_max = GetMinMax(array, begin, end);

      if (with_files) {
        char file_name[64];
        GetResultFileName(file_name, sizeof(file_name), parent_pid, i);

        FILE *file = fopen(file_name, "w");
        if (file == NULL) {
          perror("fopen");
          _exit(1);
        }

        if (fprintf(file, "%d %d\n", local_min_max.min, local_min_max.max) < 0) {
          perror("fprintf");
          fclose(file);
          _exit(1);
        }

        if (fclose(file) != 0) {
          perror("fclose");
          _exit(1);
        }
      } else {
        for (int j = 0; j < pnum; j++) {
          close(pipes[j][0]);
          if (j != i) {
            close(pipes[j][1]);
          }
        }

        ssize_t bytes_written =
            write(pipes[i][1], &local_min_max, sizeof(local_min_max));
        if (bytes_written != (ssize_t)sizeof(local_min_max)) {
          perror("write");
          close(pipes[i][1]);
          _exit(1);
        }
        close(pipes[i][1]);
      }

      free(pipes);
      free(child_pids);
      free(array);
      _exit(0);
    }

    child_pids[i] = child_pid;
    active_child_processes++;
  }

  if (!with_files) {
    for (int i = 0; i < pnum; i++) {
      close(pipes[i][1]);
    }
  }

  bool child_failed = false;
  for (int i = 0; i < active_child_processes; i++) {
    int status = 0;
    if (waitpid(child_pids[i], &status, 0) == -1) {
      perror("waitpid");
      child_failed = true;
      continue;
    }

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
      child_failed = true;
    }
  }

  if (fork_failed || child_failed) {
    if (!with_files) {
      for (int i = 0; i < pnum; i++) {
        close(pipes[i][0]);
      }
    } else {
      for (int i = 0; i < active_child_processes; i++) {
        char file_name[64];
        GetResultFileName(file_name, sizeof(file_name), parent_pid, i);
        remove(file_name);
      }
    }

    free(pipes);
    free(child_pids);
    free(array);
    return 1;
  }

  struct MinMax min_max;
  min_max.min = INT_MAX;
  min_max.max = INT_MIN;

  for (int i = 0; i < pnum; i++) {
    int min = INT_MAX;
    int max = INT_MIN;

    if (with_files) {
      char file_name[64];
      GetResultFileName(file_name, sizeof(file_name), parent_pid, i);

      FILE *file = fopen(file_name, "r");
      if (file == NULL) {
        perror("fopen");
        free(child_pids);
        free(array);
        return 1;
      }

      if (fscanf(file, "%d %d", &min, &max) != 2) {
        fprintf(stderr, "Failed to read result from %s\n", file_name);
        fclose(file);
        remove(file_name);
        free(child_pids);
        free(array);
        return 1;
      }

      fclose(file);
      remove(file_name);
    } else {
      struct MinMax local_min_max;
      ssize_t bytes_read =
          read(pipes[i][0], &local_min_max, sizeof(local_min_max));
      close(pipes[i][0]);

      if (bytes_read != (ssize_t)sizeof(local_min_max)) {
        fprintf(stderr, "Failed to read result from child %d\n", i);
        free(pipes);
        free(child_pids);
        free(array);
        return 1;
      }

      min = local_min_max.min;
      max = local_min_max.max;
    }

    if (min < min_max.min) {
      min_max.min = min;
    }
    if (max > min_max.max) {
      min_max.max = max;
    }
  }

  struct timeval finish_time;
  gettimeofday(&finish_time, NULL);

  double elapsed_time = (finish_time.tv_sec - start_time.tv_sec) * 1000.0;
  elapsed_time += (finish_time.tv_usec - start_time.tv_usec) / 1000.0;

  free(pipes);
  free(child_pids);
  free(array);

  printf("Min: %d\n", min_max.min);
  printf("Max: %d\n", min_max.max);
  printf("Elapsed time: %fms\n", elapsed_time);
  fflush(NULL);

  return 0;
}
