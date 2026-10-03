#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include <getopt.h>
#include <pthread.h>

#include "sum.h"
#include "utils.h"

struct SumArgs {
  const int *array;
  unsigned int begin;
  unsigned int end;
  int64_t result;
};

static bool ParsePositiveUInt32(const char *text, uint32_t *value) {
  errno = 0;
  char *end = NULL;
  unsigned long parsed = strtoul(text, &end, 10);

  if (errno != 0 || end == text || *end != '\0' || parsed == 0 ||
      parsed > UINT32_MAX) {
    return false;
  }

  *value = (uint32_t)parsed;
  return true;
}

static void *ThreadSum(void *args) {
  struct SumArgs *sum_args = (struct SumArgs *)args;
  sum_args->result =
      Sum(sum_args->array, sum_args->begin, sum_args->end);
  return NULL;
}

static double ElapsedSeconds(const struct timespec *start,
                             const struct timespec *finish) {
  double seconds = (double)(finish->tv_sec - start->tv_sec);
  seconds += (double)(finish->tv_nsec - start->tv_nsec) / 1000000000.0;
  return seconds;
}

int main(int argc, char **argv) {
  uint32_t threads_num = 0;
  uint32_t array_size = 0;
  uint32_t seed = 0;

  static struct option options[] = {
      {"threads_num", required_argument, NULL, 't'},
      {"seed", required_argument, NULL, 's'},
      {"array_size", required_argument, NULL, 'a'},
      {0, 0, 0, 0}};

  while (true) {
    int c = getopt_long(argc, argv, "", options, NULL);
    if (c == -1) {
      break;
    }

    switch (c) {
      case 't':
        if (!ParsePositiveUInt32(optarg, &threads_num)) {
          fprintf(stderr, "threads_num is a positive number\n");
          return 1;
        }
        break;
      case 's':
        if (!ParsePositiveUInt32(optarg, &seed)) {
          fprintf(stderr, "seed is a positive number\n");
          return 1;
        }
        break;
      case 'a':
        if (!ParsePositiveUInt32(optarg, &array_size)) {
          fprintf(stderr, "array_size is a positive number\n");
          return 1;
        }
        break;
      case '?':
      default:
        return 1;
    }
  }

  if (optind < argc || threads_num == 0 || seed == 0 || array_size == 0) {
    fprintf(stderr,
            "Usage: %s --threads_num \"num\" --seed \"num\" "
            "--array_size \"num\"\n",
            argv[0]);
    return 1;
  }

  int *array = malloc((size_t)array_size * sizeof(int));
  if (array == NULL) {
    perror("malloc array");
    return 1;
  }

  /* Array generation is intentionally outside the measured interval. */
  GenerateArray(array, array_size, seed);

  pthread_t *threads = malloc((size_t)threads_num * sizeof(pthread_t));
  struct SumArgs *args =
      calloc((size_t)threads_num, sizeof(struct SumArgs));

  if (threads == NULL || args == NULL) {
    perror("allocate thread data");
    free(args);
    free(threads);
    free(array);
    return 1;
  }

  struct timespec start_time;
  struct timespec finish_time;

  if (clock_gettime(CLOCK_MONOTONIC, &start_time) == -1) {
    perror("clock_gettime");
    free(args);
    free(threads);
    free(array);
    return 1;
  }

  uint32_t created_threads = 0;
  for (uint32_t i = 0; i < threads_num; i++) {
    args[i].array = array;
    args[i].begin = (unsigned int)(((uint64_t)i * array_size) / threads_num);
    args[i].end =
        (unsigned int)(((uint64_t)(i + 1) * array_size) / threads_num);
    args[i].result = 0;

    int error = pthread_create(&threads[i], NULL, ThreadSum, &args[i]);
    if (error != 0) {
      fprintf(stderr, "pthread_create failed: error %d\n", error);
      break;
    }
    created_threads++;
  }

  if (created_threads != threads_num) {
    for (uint32_t i = 0; i < created_threads; i++) {
      pthread_join(threads[i], NULL);
    }
    free(args);
    free(threads);
    free(array);
    return 1;
  }

  bool join_failed = false;
  for (uint32_t i = 0; i < threads_num; i++) {
    int error = pthread_join(threads[i], NULL);
    if (error != 0) {
      fprintf(stderr, "pthread_join failed: error %d\n", error);
      join_failed = true;
    }
  }

  if (clock_gettime(CLOCK_MONOTONIC, &finish_time) == -1) {
    perror("clock_gettime");
    free(args);
    free(threads);
    free(array);
    return 1;
  }

  if (join_failed) {
    free(args);
    free(threads);
    free(array);
    return 1;
  }

  int64_t total_sum = 0;
  for (uint32_t i = 0; i < threads_num; i++) {
    total_sum += args[i].result;
  }

  double elapsed_time = ElapsedSeconds(&start_time, &finish_time);

  free(args);
  free(threads);
  free(array);

  printf("Total: %" PRId64 "\n", total_sum);
  printf("Elapsed time: %.9f s\n", elapsed_time);
  return 0;
}
