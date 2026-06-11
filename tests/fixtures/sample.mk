# fixture for extract_make
include common.mk

all: build test
	./scripts/run.sh

build: src/main.c
	$(CC) -o app src/main.c

test: build
	python3 tests/run_tests.py
