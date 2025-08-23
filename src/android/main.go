package main

import (
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"time"
)

const (
	serverPort       = "8000"
	smsGatewayPort   = "8080"
	version          = "0.4"
	healthCheckRetry = 10 * time.Second
	smsGatewayUser   = "sms"
	// Using SETTLER password from .env - in production this should be read from env
	smsGatewayPass   = "TOMmAyL5"
)

func main() {
	log.Printf("[%s] Starting smsgap v%s", time.Now().Format("2006-01-02 15:04:05"), version)

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
	client := NewSMSGatewayClient(smsGatewayURL, smsGatewayUser, smsGatewayPass)
	if err := SetupWebhooks(client, serverPort); err != nil {
		log.Fatalf("FATAL: Failed to setup webhooks: %v", err)
	}

	// Create and configure router
	r := SetupRouter(version)

	// Start server
	log.Printf("Starting HTTP server on port %s", serverPort)
	server := &http.Server{
		Addr:    ":" + serverPort,
		Handler: r,
	}

	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("FATAL: Failed to start server: %v", err)
		os.Exit(1)
	}
}