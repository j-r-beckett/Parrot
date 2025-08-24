package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

const (
	serverPort       = "8000"
	smsGatewayPort   = "8080"
	version          = "1.7"
	healthCheckRetry = 10 * time.Second
	smsGatewayUser   = "sms"
	passwordFile     = "/data/adb/smsgap/password.txt"
)

func main() {
	log.Printf("[%s] Starting smsgap v%s", time.Now().Format("2006-01-02 15:04:05"), version)

	// Read SMS Gateway password from file
	passwordBytes, err := os.ReadFile(passwordFile)
	if err != nil {
		log.Fatalf("FATAL: Failed to read password file %s: %v", passwordFile, err)
	}
	smsGatewayPass := strings.TrimSpace(string(passwordBytes))
	
	// Check if port is available
	listener, err := net.Listen("tcp", ":"+serverPort)
	if err != nil {
		log.Fatalf("FATAL: Port %s is not available: %v", serverPort, err)
	}
	listener.Close()
	
	// Wait for SMS Gateway to be available
	log.Printf("Checking SMS Gateway health on port %s", smsGatewayPort)
	smsGatewayURL := fmt.Sprintf("http://localhost:%s", smsGatewayPort)
	startTime := time.Now()
	for {
		err := CheckSMSGatewayHealth(smsGatewayURL)
		if err == nil {
			log.Printf("SMS Gateway is healthy")
			break
		}
		
		if time.Since(startTime) > healthCheckRetry {
			log.Fatalf("FATAL: SMS Gateway not available after %v: %v", healthCheckRetry, err)
		}
		
		log.Printf("SMS Gateway not ready: %v, retrying...", err)
		time.Sleep(1 * time.Second)
	}
	
	// Setup webhooks with SMS Gateway
	smsClient := NewSMSGatewayClient(smsGatewayURL, smsGatewayUser, smsGatewayPass)
	if err := SetupWebhooks(smsClient, serverPort); err != nil {
		log.Fatalf("FATAL: Failed to setup webhooks: %v", err)
	}

	// Create client manager and start pruning
	clientManager := NewClientManager()
	clientManager.StartPruning()
	
	// Start webhook auto-repair goroutine
	stopAutoRepair := make(chan struct{})
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		
		for {
			select {
			case <-ticker.C:
				if err := RepairWebhooks(smsClient, serverPort); err != nil {
					log.Printf("[WebhookAutoRepair] ERROR: Failed to repair webhooks: %v", err)
				}
			case <-stopAutoRepair:
				log.Printf("[WebhookAutoRepair] Stopping auto-repair")
				return
			}
		}
	}()
	
	// Create and configure router
	r := SetupRouter(version, clientManager, smsClient)

	// Start server
	log.Printf("Starting HTTP server on port %s", serverPort)
	server := &http.Server{
		Addr:    ":" + serverPort,
		Handler: r,
	}

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	
	// Start server in goroutine
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("FATAL: Failed to start server: %v", err)
		}
	}()
	
	// Wait for shutdown signal
	<-sigChan
	log.Printf("Shutting down gracefully...")
	
	// Stop auto-repair
	close(stopAutoRepair)
	
	// Stop client manager pruning
	clientManager.Stop()
	
	// Shutdown HTTP server (waits for active requests to complete)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	
	if err := server.Shutdown(ctx); err != nil {
		log.Printf("ERROR: Server shutdown failed: %v", err)
	}
	
	// Clean up webhooks from SMS Gateway
	if err := CleanupWebhooks(smsClient); err != nil {
		log.Printf("ERROR: Failed to cleanup webhooks: %v", err)
	}
	
	log.Printf("Server stopped")
}