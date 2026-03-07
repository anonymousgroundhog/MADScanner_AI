# Variables
PYTHON = python3
VENV = venv
BIN = $(VENV)/bin
EXTERNAL_LIBS = appium-python-client graphviz selenium web3

# OS Detection
OS := $(shell uname -s)

.PHONY: all venv install clean system-deps node-deps

all: system-deps node-deps venv install

# 1. Install System-Level Dependencies (Graphviz)
system-deps:
	@echo "Checking System Dependencies..."
ifeq ($(OS), Darwin)
	@which brew >/dev/null 2>&1 || (echo "Homebrew not found."; exit 1)
	@brew list graphviz >/dev/null 2>&1 || brew install graphviz
else ifeq ($(OS), Linux)
	@if [ -f /etc/debian_version ]; then \
		sudo apt-get update && sudo apt-get install -y graphviz python3-venv python3-pip curl; \
	fi
endif

# 2. Install Node.js and Appium Server
node-deps:
	@echo "Checking Node.js for Appium Server..."
	@which node >/dev/null 2>&1 || ( \
		echo "Node.js not found. Installing..." && \
		if [ "$(OS)" = "Darwin" ]; then brew install node; \
		else curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs; fi \
	)
	@echo "Installing Appium Server globally..."
	@sudo npm install -g appium
	@appium driver install chromium  # Required for Selenium/Web tests

# 3. Create the Python Virtual Environment
venv:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)

# 4. Install Python Libraries
install: venv
	@echo "Installing Python libraries..."
	@$(BIN)/pip install --upgrade pip
	@$(BIN)/pip install $(EXTERNAL_LIBS)
	@echo "--- SETUP COMPLETE ---"
	@echo "To start Appium Server: appium"
	@echo "To run your script: ./$(BIN)/python your_script.py"

clean:
	rm -rf $(VENV)
	@echo "Environment cleaned."
