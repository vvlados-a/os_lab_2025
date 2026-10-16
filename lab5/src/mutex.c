#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The same source is compiled with and without -DUSE_MUTEX. */
static int common = 0;
static pthread_mutex_t mut = PTHREAD_MUTEX_INITIALIZER;

static void *do_one_thing(void *arg) {
    int *counter = arg;
    for (int i = 0; i < 50; ++i) {
#ifdef USE_MUTEX
        pthread_mutex_lock(&mut);
#endif
        int work = *counter;
        for (volatile unsigned long k = 0; k < 500000; ++k) {
        }
        *counter = work + 1;
#ifdef USE_MUTEX
        pthread_mutex_unlock(&mut);
#endif
    }
    return NULL;
}

static void *do_another_thing(void *arg) {
    int *counter = arg;
    for (int i = 0; i < 50; ++i) {
#ifdef USE_MUTEX
        pthread_mutex_lock(&mut);
#endif
        int work = *counter;
        for (volatile unsigned long k = 0; k < 500000; ++k) {
        }
        *counter = work + 1;
#ifdef USE_MUTEX
        pthread_mutex_unlock(&mut);
#endif
    }
    return NULL;
}

int main(void) {
    pthread_t thread1, thread2;
    int error = pthread_create(&thread1, NULL, do_one_thing, &common);
    if (error != 0) {
        fprintf(stderr, "pthread_create: %s\n", strerror(error));
        return 1;
    }

    error = pthread_create(&thread2, NULL, do_another_thing, &common);
    if (error != 0) {
        fprintf(stderr, "pthread_create: %s\n", strerror(error));
        pthread_join(thread1, NULL);
        return 1;
    }

    pthread_join(thread1, NULL);
    pthread_join(thread2, NULL);
    printf("All done, counter = %d\n", common);
    pthread_mutex_destroy(&mut);
    return 0;
}
