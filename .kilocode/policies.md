sandbox:
  allowed_commands:
    - uv
    - python
    - python3
    - bash
    - ls
    - find
    - cat
    - head
    - tail
    - grep
    - rg
    - wc
    - mkdir
    - cp
    - mv

filesystem:
  writable_paths:
    - data/extracted
    - data/cleaned
    - data/chunks
    - data/metadata
    - vectorstore
    - outputs

  readable_paths:
    - data/raw
    - data/extracted
    - data/cleaned
    - data/chunks
    - data/metadata
    - vectorstore
    - outputs
    - nanoclaw
    - src
