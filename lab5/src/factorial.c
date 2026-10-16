#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Task {
    uint64_t begin;
    uint64_t end;
    uint64_t mod;
};

static uint64_t result;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;

static int parse_number(const char *text, uint64_t *number) {
    char *end;
    errno = 0;
    if (*text == '-' || *text == '\0') return 0;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno != 0 || *end != '\0') return 0;
    *number = (uint64_t)value;
    return 1;
}

static void *factorial_part(void *arg) {
    const struct Task *task = arg;
    uint64_t part = 1 % task->mod;

    for (uint64_t i = task->begin; i <= task->end && i != 0; ++i) {
        part = (uint64_t)(((__uint128_t)part * (i % task->mod)) % task->mod);
        if (i == task->end) break;
    }

    pthread_mutex_lock(&mutex);
    result = (uint64_t)(((__uint128_t)result * part) % task->mod);
    pthread_mutex_unlock(&mutex);
    return NULL;
}

int main(int argc, char **argv) {
    uint64_t k = 0, mod = 0, pnum = 0;
    int have_k = 0, have_mod = 0, have_pnum = 0;
    static const struct option options[] = {
        {"pnum", required_argument, NULL, 'p'},
        {"mod", required_argument, NULL, 'm'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "k:", options, NULL)) != -1) {
        switch (opt) {
            case 'k': have_k = parse_number(optarg, &k); break;
            case 'p': have_pnum = parse_number(optarg, &pnum); break;
            case 'm': have_mod = parse_number(optarg, &mod); break;
            default: return 1;
        }
    }
    if (!have_k || !have_pnum || !have_mod || pnum == 0 || mod == 0 ||
        optind != argc || pnum > SIZE_MAX / sizeof(pthread_t) ||
        pnum > SIZE_MAX / sizeof(struct Task)) {
        fprintf(stderr, "Usage: %s -k K --pnum=N --mod=M (N >= 1, M >= 1)\n", argv[0]);
        return 1;
    }

    pthread_t *threads = malloc((size_t)pnum * sizeof(*threads));
    struct Task *tasks = malloc((size_t)pnum * sizeof(*tasks));
    if (!threads || !tasks) {
        perror("malloc");
        free(threads);
        free(tasks);
        return 1;
    }

    result = 1 % mod;
    uint64_t start = 1;
    uint64_t part_size = k / pnum;
    uint64_t remainder = k % pnum;
    uint64_t created = 0;

    for (uint64_t i = 0; i < pnum; ++i) {
        uint64_t count = part_size + (i < remainder);
        tasks[i].begin = start;
        tasks[i].end = start + count - 1;
        tasks[i].mod = mod;
        if (count != 0) start = tasks[i].end + 1;

        int error = pthread_create(&threads[i], NULL, factorial_part, &tasks[i]);
        if (error != 0) {
            fprintf(stderr, "pthread_create: %s\n", strerror(error));
            break;
        }
        ++created;
    }

    for (uint64_t i = 0; i < created; ++i) pthread_join(threads[i], NULL);

    if (created == pnum) printf("%" PRIu64 "! %% %" PRIu64 " = %" PRIu64 "\n", k, mod, result);
    pthread_mutex_destroy(&mutex);
    free(threads);
    free(tasks);
    return created == pnum ? 0 : 1;
}
