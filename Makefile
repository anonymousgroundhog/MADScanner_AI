# Variables
PYTHON = python3
PIP = pip3
EXTERNAL_LIBS = appium-python-client graphviz selenium web3
APK_DIR = APK_Files_To_Analyze

# OS Detection
OS := $(shell uname -s)

.PHONY: all install clean system-deps node-deps

# Main setup sequence
all: system-deps node-deps install

# 1. Install System-Level Dependencies
system-deps:
	@echo "Checking System Dependencies..."
ifeq ($(OS), Darwin)
	@which brew >/dev/null 2>&1 || (echo "Homebrew not found."; exit 1)
	@brew list graphviz >/dev/null 2>&1 || brew install graphviz
else ifeq ($(OS), Linux)
	@if [ -f /etc/debian_version ]; then \
		sudo apt-get update && sudo apt-get install -y graphviz python3-pip curl; \
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
	@sudo npm install -g appium
	@appium driver install chromium

# 3. Install Python Libraries and Create Directory
install:
	@echo "Installing Python libraries..."
	$(PIP) install --upgrade pip
	$(PIP) install $(EXTERNAL_LIBS)
	@echo "Ensuring analysis directory exists..."
	mkdir -p $(APK_DIR)
	@echo "--- SETUP COMPLETE ---"
	@echo "Directory created: $(APK_DIR)"

# 4. Clean up environment
clean:
	@echo "Cleaning up..."
	rm -rf venv
	rm -rf '7]' '.
