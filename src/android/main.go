package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
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
	// Using SETTLER password from .env - in production this should be read from env
	smsGatewayPass   = "TOMmAyL5"
)

type SMSGatewayClient struct {
	baseURL  string
	username string
	password string
	client   *http.Client
}

type Webhook struct {
	ID    string `json:"id"`
	URL   string `json:"url"`
	Event string `json:"event"`
}

type WebhookRegistration struct {
	URL   string `json:"url"`
	Event string `json:"event"`
}

func NewSMSGatewayClient() *SMSGatewayClient {
	return &SMSGatewayClient{
		baseURL:  fmt.Sprintf("http://localhost:%s", smsGatewayPort),
		username: smsGatewayUser,
		password: smsGatewayPass,
		client:   &http.Client{Timeout: 5 * time.Second},
	}
}

func (c *SMSGatewayClient) doRequest(method, path string, body interface{}) (*http.Response, error) {
	var reqBody io.Reader
	if body != nil {
		jsonBody, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reqBody = bytes.NewBuffer(jsonBody)
	}
	
	req, err := http.NewRequest(method, c.baseURL+path, reqBody)
	if err != nil {
		return nil, err
	}
	
	req.SetBasicAuth(c.username, c.password)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	
	return c.client.Do(req)
}

func (c *SMSGatewayClient) GetWebhooks() ([]Webhook, error) {
	resp, err := c.doRequest("GET", "/webhooks", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to get webhooks: status %d, body: %s", resp.StatusCode, body)
	}
	
	var webhooks []Webhook
	if err := json.NewDecoder(resp.Body).Decode(&webhooks); err != nil {
		return nil, err
	}
	
	return webhooks, nil
}

func (c *SMSGatewayClient) DeleteWebhook(id string) error {
	resp, err := c.doRequest("DELETE", "/webhooks/"+id, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to delete webhook: status %d, body: %s", resp.StatusCode, body)
	}
	
	return nil
}

func (c *SMSGatewayClient) RegisterWebhook(event string) error {
	webhook := WebhookRegistration{
		URL:   fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", serverPort, event),
		Event: event,
	}
	
	resp, err := c.doRequest("POST", "/webhooks", webhook)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to register webhook: status %d, body: %s", resp.StatusCode, body)
	}
	
	return nil
}

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

func setupWebhooks() error {
	client := NewSMSGatewayClient()
	
	// Get existing webhooks
	log.Printf("Getting existing webhooks")
	webhooks, err := client.GetWebhooks()
	if err != nil {
		return fmt.Errorf("failed to get webhooks: %v", err)
	}
	
	// Delete all existing webhooks
	for _, webhook := range webhooks {
		log.Printf("Deleting webhook %s for event %s", webhook.ID, webhook.Event)
		if err := client.DeleteWebhook(webhook.ID); err != nil {
			return fmt.Errorf("failed to delete webhook %s: %v", webhook.ID, err)
		}
	}
	
	// Register new webhook for sms:received only (Phase 1.4)
	log.Printf("Registering webhook for sms:received")
	if err := client.RegisterWebhook("sms:received"); err != nil {
		return fmt.Errorf("failed to register webhook: %v", err)
	}
	
	log.Printf("Webhook registration complete")
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
	
	// Setup webhooks with SMS Gateway
	if err := setupWebhooks(); err != nil {
		log.Fatalf("FATAL: Failed to setup webhooks: %v", err)
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
	
	// Webhook endpoint for sms:received - stub that logs and returns 200
	r.Post("/webhook/sms:received", func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			log.Printf("ERROR: Failed to read webhook body: %v", err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		
		log.Printf("Received webhook sms:received - body: %s", string(body))
		
		// Return 200 OK immediately
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
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