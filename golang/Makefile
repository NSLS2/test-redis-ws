# Define the binary name
BINARY_NAME=nats-ws

# Define the artifact path with a default value
ARTIFACT_PATH ?= ./product

# Define the full binary path
BINARY_PATH=$(ARTIFACT_PATH)/$(BINARY_NAME)

# Ensure the artifact path exists
$(ARTIFACT_PATH):
	mkdir -p $(ARTIFACT_PATH)

# Define the main package path, should really be main.go with proper package structure
MAIN_PACKAGE=./server_nats.go

# Default target
all: darwin-arm64 linux

# Helper function to build for a specific OS and architecture
define build
	GOOS=$(1) GOARCH=$(2) go build $(LDFLAGS) -o $(BINARY_PATH)-$(1)-$(2) $(MAIN_PACKAGE)
endef

# Build for Linux (Intel)
linux: $(ARTIFACT_PATH)
	$(call build,linux,amd64)

# Build for Linux (ARM)
linux-arm64: $(ARTIFACT_PATH)
	$(call build,linux,arm64)

# Build for macOS (Intel)
darwin: $(ARTIFACT_PATH)
	$(call build,darwin,amd64)

# Build for macOS (Apple Silicon)
darwin-arm64: $(ARTIFACT_PATH)
	$(call build,darwin,arm64)

# Build for Windows (64-bit)
windows: $(ARTIFACT_PATH)
	$(call build,windows,amd64)

# Clean up build artifacts
clean:
	rm -rf $(ARTIFACT_PATH)

tidy:
	go mod tidy

.PHONY: all linux darwin darwin-arm64 windows clean tidy
