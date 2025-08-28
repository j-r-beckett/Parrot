package main

import (
	"context"
	"flag"
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
	smsGatewayPort   = "8080"
	version          = "1.8"
	healthCheckRetry = 10 * time.Second
	smsGatewayUser   = "sms"
	passwordFile     = "/data/adb/smsgap/password.txt"
)

// getLocalIP returns the device's local network IP address
func getLocalIP() (string, error) {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return "", err
	}

	for _, addr := range addrs {
		if ipnet, ok := addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil && ipnet.IP.IsPrivate() {
				return ipnet.IP.String(), nil
			}
		}
	}
	return "", fmt.Errorf("no local IP address found")
}

func main() {
	log.Printf("[%s] Starting smsgap v%s", time.Now().Format("2006-01-02 15:04:05"), version)

	// Parse command line arguments
	var passwordArg, port, privateIP string
	flag.StringVar(&passwordArg, "password", "", "SMS Gateway password (optional, uses password file if not specified)")
	flag.StringVar(&port, "port", "", "Port to bind to (required)")
	flag.StringVar(&privateIP, "private-ip", "", "Private IP address to restrict API access to (required)")
	flag.Parse()
	log.Printf("DEBUG: After parse, password flag = %q", passwordArg)

	// Validate required arguments
	if port == "" {
		log.Fatalf("FATAL: -port argument is required")
	}
	if privateIP == "" {
		log.Fatalf("FATAL: -private-ip argument is required")
	}

	// Always bind to all interfaces
	host := "0.0.0.0"

	// Get SMS Gateway password from command line or file
	var smsGatewayPass string
	if passwordArg != "" {
		smsGatewayPass = passwordArg
		log.Printf("Using password from command line argument")
	} else {
		// Read SMS Gateway password from file
		passwordBytes, err := os.ReadFile(passwordFile)
		if err != nil {
			log.Fatalf("FATAL: Failed to read password file %s: %v (use -password flag to provide password via command line)", passwordFile, err)
		}
		smsGatewayPass = strings.TrimSpace(string(passwordBytes))
		log.Printf("Using password from file %s", passwordFile)
	}

	// Check if API server port is available
	serverAddr := net.JoinHostPort(host, port)
	listener, err := net.Listen("tcp", serverAddr)
	if err != nil {
		log.Fatalf("FATAL: Address %s is not available: %v", serverAddr, err)
	}
	listener.Close()

	// Find an available port for webhook server
	webhookListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatalf("FATAL: Failed to find available port for webhook server: %v", err)
	}
	webhookPort := fmt.Sprintf("%d", webhookListener.Addr().(*net.TCPAddr).Port)
	webhookListener.Close()
	log.Printf("Using port %s for webhook server", webhookPort)

	// Get local IP to connect to SMS Gateway
	localIP, err := getLocalIP()
	if err != nil {
		log.Fatalf("FATAL: Failed to get local IP: %v", err)
	}
	log.Printf("Detected local IP: %s", localIP)

	// Wait for SMS Gateway to be available
	log.Printf("Checking SMS Gateway health on port %s", smsGatewayPort)
	smsGatewayURL := fmt.Sprintf("http://%s:%s", localIP, smsGatewayPort)
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
	if err := SetupWebhooks(smsClient, webhookPort); err != nil {
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
				if err := RepairWebhooks(smsClient, webhookPort); err != nil {
					log.Printf("[WebhookAutoRepair] ERROR: Failed to repair webhooks: %v", err)
				}
			case <-stopAutoRepair:
				log.Printf("[WebhookAutoRepair] Stopping auto-repair")
				return
			}
		}
	}()

	// Create routers
	apiRouter := SetupAPIRouter(version, clientManager, smsClient, privateIP)
	webhookRouter := SetupWebhookRouter(clientManager)

	// Start API server on host:port
	log.Printf("Starting API server on %s", serverAddr)
	apiServer := &http.Server{
		Addr:    serverAddr,
		Handler: apiRouter,
	}

	// Start webhook server on 127.0.0.1:webhookPort
	webhookAddr := net.JoinHostPort("127.0.0.1", webhookPort)
	log.Printf("Starting webhook server on %s", webhookAddr)
	webhookServer := &http.Server{
		Addr:    webhookAddr,
		Handler: webhookRouter,
	}

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Start both servers in goroutines
	go func() {
		if err := apiServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("FATAL: Failed to start API server: %v", err)
		}
	}()

	go func() {
		if err := webhookServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("FATAL: Failed to start webhook server: %v", err)
		}
	}()

	// Wait for shutdown signal
	<-sigChan
	log.Printf("Shutting down gracefully...")

	// Stop auto-repair
	close(stopAutoRepair)

	// Stop client manager pruning
	clientManager.Stop()

	// Shutdown both HTTP servers (waits for active requests to complete)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := apiServer.Shutdown(ctx); err != nil {
		log.Printf("ERROR: API server shutdown failed: %v", err)
	}

	if err := webhookServer.Shutdown(ctx); err != nil {
		log.Printf("ERROR: Webhook server shutdown failed: %v", err)
	}

	// Clean up webhooks from SMS Gateway
	if err := CleanupWebhooks(smsClient); err != nil {
		log.Printf("ERROR: Failed to cleanup webhooks: %v", err)
	}

	log.Printf("Server stopped")
}
