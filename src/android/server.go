package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"regexp"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

var phoneNumberRegex = regexp.MustCompile(`^\+?\d{10,14}$`)

// RegisterRequest represents the client registration request
type RegisterRequest struct {
	ID                  string   `json:"id"`
	WebhookURL          string   `json:"webhook_url"`
	SmsReceived         bool     `json:"sms_received"`
	SmsSent             bool     `json:"sms_sent"`
	SmsDelivered        bool     `json:"sms_delivered"`
	SmsFailed           bool     `json:"sms_failed"`
	IncludeReceivedFrom []string `json:"include_received_from,omitempty"`
	ExcludeReceivedFrom []string `json:"exclude_received_from,omitempty"`
}

// SetupRouter creates and configures the HTTP router
func SetupRouter(version string, clientManager *ClientManager, smsClient *SMSGatewayClient) *chi.Mux {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Health endpoint
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		
		// Check SMS Gateway health
		err := smsClient.CheckHealth()
		
		if err == nil {
			w.WriteHeader(http.StatusOK)
			fmt.Fprintf(w, `{"status":"healthy","version":"%s","timestamp":"%s","sms_gateway":"healthy"}`, 
				version, time.Now().Format(time.RFC3339))
		} else {
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprintf(w, `{"status":"unhealthy","version":"%s","timestamp":"%s","sms_gateway":"unhealthy","error":"%s"}`, 
				version, time.Now().Format(time.RFC3339), err.Error())
		}
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
		
		// Validate that both include and exclude lists are not specified
		if len(req.IncludeReceivedFrom) > 0 && len(req.ExcludeReceivedFrom) > 0 {
			http.Error(w, "Cannot specify both include_received_from and exclude_received_from", http.StatusBadRequest)
			return
		}
		
		// Validate phone numbers if provided
		for _, num := range req.IncludeReceivedFrom {
			if !phoneNumberRegex.MatchString(num) {
				http.Error(w, fmt.Sprintf("Invalid phone number in include_received_from: %s", num), http.StatusBadRequest)
				return
			}
		}
		for _, num := range req.ExcludeReceivedFrom {
			if !phoneNumberRegex.MatchString(num) {
				http.Error(w, fmt.Sprintf("Invalid phone number in exclude_received_from: %s", num), http.StatusBadRequest)
				return
			}
		}
		
		// Register the client
		client := &Client{
			ID:                  req.ID,
			WebhookURL:          req.WebhookURL,
			SmsReceived:         req.SmsReceived,
			SmsSent:             req.SmsSent,
			SmsDelivered:        req.SmsDelivered,
			SmsFailed:           req.SmsFailed,
			IncludeReceivedFrom: req.IncludeReceivedFrom,
			ExcludeReceivedFrom: req.ExcludeReceivedFrom,
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
	
	// Send SMS endpoint (proxy to SMS Gateway)
	r.Post("/send", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			PhoneNumbers []string `json:"phone_numbers"`
			Message      string   `json:"message"`
			SimNumber    *int     `json:"sim_number,omitempty"`
		}
		
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid JSON", http.StatusBadRequest)
			return
		}
		
		// Validate required fields
		if len(req.PhoneNumbers) == 0 {
			http.Error(w, "phone_numbers is required", http.StatusBadRequest)
			return
		}
		if req.Message == "" {
			http.Error(w, "message is required", http.StatusBadRequest)
			return
		}
		
		// Send SMS via SMS Gateway
		result, err := smsClient.SendSMS(req.PhoneNumbers, req.Message, req.SimNumber)
		if err != nil {
			log.Printf("ERROR: Failed to send SMS: %v", err)
			http.Error(w, fmt.Sprintf("Failed to send SMS: %v", err), http.StatusInternalServerError)
			return
		}
		
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(result)
	})
	
	// Webhook endpoints
	r.Post("/webhook/received", CreateWebhookHandler("received", clientManager))
	r.Post("/webhook/sent", CreateWebhookHandler("sent", clientManager))
	r.Post("/webhook/delivered", CreateWebhookHandler("delivered", clientManager))
	r.Post("/webhook/failed", CreateWebhookHandler("failed", clientManager))

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
		// Remove sms: prefix
		eventPath := event[4:]
		callbackURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", serverPort, eventPath)
		if err := client.RegisterWebhook(event, callbackURL); err != nil {
			return fmt.Errorf("failed to register webhook for %s: %v", event, err)
		}
	}
	
	log.Printf("Webhook registration complete")
	return nil
}

// RepairWebhooks checks if our webhooks are registered and repairs them if needed
func RepairWebhooks(client *SMSGatewayClient, serverPort string) error {
	log.Printf("[WebhookAutoRepair] Checking webhook registrations")
	
	// Get current webhooks
	webhooks, err := client.GetWebhooks()
	if err != nil {
		return fmt.Errorf("failed to get webhooks: %v", err)
	}
	
	// Build a map of what we have
	existingWebhooks := make(map[string]bool)
	for _, webhook := range webhooks {
		// Remove sms: prefix
		eventPath := webhook.Event[4:]
		expectedURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", serverPort, eventPath)
		if webhook.URL == expectedURL {
			existingWebhooks[webhook.Event] = true
		} else {
			// Wrong URL, delete it
			log.Printf("[WebhookAutoRepair] Found webhook with wrong URL for %s. Expected %s, got %s. Deleting...", 
				webhook.Event, expectedURL, webhook.URL)
			if err := client.DeleteWebhook(webhook.ID); err != nil {
				log.Printf("[WebhookAutoRepair] ERROR: Failed to delete webhook %s: %v", webhook.ID, err)
			}
		}
	}
	
	// Check and repair each event type
	webhookEvents := []string{"sms:received", "sms:sent", "sms:delivered", "sms:failed"}
	repaired := 0
	for _, event := range webhookEvents {
		if !existingWebhooks[event] {
			log.Printf("[WebhookAutoRepair] Webhook missing for %s, repairing...", event)
			// Remove sms: prefix
			eventPath := event[4:]
			callbackURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", serverPort, eventPath)
			if err := client.RegisterWebhook(event, callbackURL); err != nil {
				log.Printf("[WebhookAutoRepair] ERROR: Failed to register webhook for %s: %v", event, err)
			} else {
				repaired++
			}
		}
	}
	
	if repaired > 0 {
		log.Printf("[WebhookAutoRepair] Repaired %d webhooks", repaired)
	} else {
		log.Printf("[WebhookAutoRepair] All webhooks are correctly registered")
	}
	
	return nil
}