#include "sum.h"

int64_t Sum(const int *array, unsigned int begin, unsigned int end) {
  int64_t sum = 0;

  for (unsigned int i = begin; i < end; i++) {
    sum += array[i];
  }

  return sum;
}
