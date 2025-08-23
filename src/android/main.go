package main

import (
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

const (
	serverPort       = "8000"
	smsGatewayPort   = "8080"
	version          = "0.3"
	healthCheckRetry = 10 * time.Second
	smsGatewayUser   = "sms"
)

func checkSMSGatewayHealth() error {
	client := &http.Client{Timeout: 2 * time.Second}
	url := fmt.Sprintf("http://localhost:%s/health", smsGatewayPort)
	
	resp, err := client.Get(url)
	if err != nil {
		return fmt.Errorf("failed to connect to SMS Gateway: %v", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("SMS Gateway health check returned status %d", resp.StatusCode)
	}
	
	return nil
}

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
	startTime := time.Now()
	for {
		err := checkSMSGatewayHealth()
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

	// Create router
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Health endpoint
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"status":"healthy","version":"%s","timestamp":"%s"}`, version, time.Now().Format(time.RFC3339))
	})

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