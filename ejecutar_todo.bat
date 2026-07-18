@echo off
lms unload --all
lms load gemma-3-4b-it-abliterated
python main.py --model "gemma-3-4b-it-abliterated" --mode backtest
lms unload gemma-3-4b-it-abliterated
lms load gemma-4-hacking
python main.py --model "gemma-4-hacking" --mode backtest
lms unload gemma-4-hacking
lms load llama-3.2-3b-instruct
python main.py --model "llama-3.2-3b-instruct" --mode backtest
lms unload llama-3.2-3b-instruct
lms load qwen2.5-7b-instruct-1m
python main.py --model "qwen2.5-7b-instruct-1m" --mode backtest
lms unload qwen2.5-7b-instruct-1m
lms load qwen3.5-2b-claude-opus-4.6-high-resoning-base-i1
python main.py --model "qwen3.5-2b-claude-opus-4.6-high-resoning-base-i1" --mode backtest
lms unload qwen3.5-2b-claude-opus-4.6-high-resoning-base-i1
lms load deepseek-r1-distill-llama-3b
python main.py --model "deepseek-r1-distill-llama-3b" --mode backtest
lms unload deepseek-r1-distill-llama-3b
pause