.PHONY: help all ingest index quiz eval clean

TOPIC      ?= GPU monitoring with DCGM
NUM        ?= 10
DIFFICULTY ?= medium

help:
	@echo "NanoClaw quiz pipeline"
	@echo ""
	@echo "Usage:"
	@echo "  make ingest                          Parse, clean, chunk and manifest raw docs"
	@echo "  make index                           Embed chunks and upsert into Qdrant"
	@echo "  make quiz [TOPIC=...] [NUM=...] [DIFFICULTY=...]"
	@echo "                                       Generate, validate and export a quiz"
	@echo "  make eval [TOPIC=...]                Re-validate and export an existing quiz"
	@echo "  make all  [TOPIC=...] [NUM=...] [DIFFICULTY=...]"
	@echo "                                       Run full pipeline: ingest → index → quiz"
	@echo "  make clean                           Remove all generated artifacts (keeps data/raw/)"
	@echo ""
	@echo "Defaults: TOPIC=\"$(TOPIC)\"  NUM=$(NUM)  DIFFICULTY=$(DIFFICULTY)"

all: ingest index quiz

ingest:
	bash nanoclaw/tasks/ingest.sh

index:
	bash nanoclaw/tasks/build_index.sh

quiz:
	bash nanoclaw/tasks/generate_quiz.sh "$(TOPIC)" $(NUM) $(DIFFICULTY)

eval:
	bash nanoclaw/tasks/eval_quiz.sh "$(TOPIC)"

clean:
	rm -rf data/extracted data/cleaned data/chunks data/metadata \
	       vectorstore/qdrant \
	       outputs/quizzes outputs/answer_keys outputs/rationales outputs/reports
	@echo "Cleaned. Raw files in data/raw/ are untouched."
