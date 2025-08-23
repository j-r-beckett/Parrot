package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

// RegisterRequest represents the client registration request
type RegisterRequest struct {
	ID           string `json:"id"`
	WebhookURL   string `json:"webhook_url"`
	SmsReceived  bool   `json:"sms_received"`
	SmsSent      bool   `json:"sms_sent"`
	SmsDelivered bool   `json:"sms_delivered"`
	SmsFailed    bool   `json:"sms_failed"`
}

// SetupRouter creates and configures the HTTP router
func SetupRouter(version string, clientManager *ClientManager) *chi.Mux {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Health endpoint
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"status":"healthy","version":"%s","timestamp":"%s"}`, version, time.Now().Format(time.RFC3339))
	})
	
	// Client registration endpoint
	r.Post("/register", func(w http.ResponseWriter, r *http.Request) {
		var req RegisterRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid JSON", http.StatusBadRequest)
			return
		}
		
		// Validate ID length
		if len(req.ID) == 0 || len(req.ID) > 128 {
			http.Error(w, "ID must be between 1 and 128 characters", http.StatusBadRequest)
			return
		}
		
		// Validate webhook URL
		if req.WebhookURL == "" {
			http.Error(w, "webhook_url is required", http.StatusBadRequest)
			return
		}
		
		// Register the client
		client := &Client{
			WebhookURL:   req.WebhookURL,
			SmsReceived:  req.SmsReceived,
			SmsSent:      req.SmsSent,
			SmsDelivered: req.SmsDelivered,
			SmsFailed:    req.SmsFailed,
		}
		
		clientManager.Register(req.ID, client)
		
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "registered", "id": req.ID})
	})
	
	// List clients endpoint
	r.Get("/clients", func(w http.ResponseWriter, r *http.Request) {
		clients := clientManager.List()
		
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(clients)
	})
	
	// Webhook endpoints
	r.Post("/webhook/sms:received", CreateWebhookHandler("sms:received", clientManager))
	r.Post("/webhook/sms:sent", CreateWebhookHandler("sms:sent", clientManager))
	r.Post("/webhook/sms:delivered", CreateWebhookHandler("sms:delivered", clientManager))
	r.Post("/webhook/sms:failed", CreateWebhookHandler("sms:failed", clientManager))

	return r
}

// CleanupWebhooks removes all our webhooks from SMS Gateway
func CleanupWebhooks(client *SMSGatewayClient) error {
	log.Printf("Cleaning up webhooks")
	webhooks, err := client.GetWebhooks()
	if err != nil {
		return fmt.Errorf("failed to get webhooks: %v", err)
	}
	
	for _, webhook := range webhooks {
		log.Printf("Deleting webhook %s for event %s", webhook.ID, webhook.Event)
		if err := client.DeleteWebhook(webhook.ID); err != nil {
			log.Printf("ERROR: Failed to delete webhook %s: %v", webhook.ID, err)
		}
	}
	
	log.Printf("Webhook cleanup complete")
	return nil
}

// SetupWebhooks clears existing webhooks and registers new ones
func SetupWebhooks(client *SMSGatewayClient, serverPort string) error {
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
	
	// Register all webhook types
	webhookEvents := []string{"sms:received", "sms:sent", "sms:delivered", "sms:failed"}
	for _, event := range webhookEvents {
		log.Printf("Registering webhook for %s", event)
		callbackURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", serverPort, event)
		if err := client.RegisterWebhook(event, callbackURL); err != nil {
			return fmt.Errorf("failed to register webhook for %s: %v", event, err)
		}
	}
	
	log.Printf("Webhook registration complete")
	return nil
}