#define _XOPEN_SOURCE 700
#include <pthread.h>
#include <stdio.h>

static pthread_mutex_t a = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t b = PTHREAD_MUTEX_INITIALIZER;
static pthread_barrier_t barrier;

static void *first(void *arg) {
    (void)arg;
    pthread_mutex_lock(&a);
    puts("Thread 1: locked A, waiting for B");
    pthread_barrier_wait(&barrier);
    pthread_mutex_lock(&b);  /* B is held by the other thread. */
    return NULL;
}

static void *second(void *arg) {
    (void)arg;
    pthread_mutex_lock(&b);
    puts("Thread 2: locked B, waiting for A");
    pthread_barrier_wait(&barrier);
    pthread_mutex_lock(&a);  /* A is held by the other thread. */
    return NULL;
}

int main(void) {
    pthread_t t1, t2;
    setbuf(stdout, NULL);
    pthread_barrier_init(&barrier, NULL, 2);
    pthread_create(&t1, NULL, first, NULL);
    pthread_create(&t2, NULL, second, NULL);
    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    return 0;
}
