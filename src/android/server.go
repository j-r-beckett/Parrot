package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"regexp"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

var phoneNumberRegex = regexp.MustCompile(`^\+?\d{10,14}$`)

// PrivateIPOnlyMiddleware restricts access to requests sent to a specific private IP
func PrivateIPOnlyMiddleware(privateIP string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get the local address the request was received on
			if addr := r.Context().Value(http.LocalAddrContextKey); addr != nil {
				if tcpAddr, ok := addr.(*net.TCPAddr); ok {
					if tcpAddr.IP.String() != privateIP {
						log.Printf("Rejecting request from %s to %s (expected %s)", r.RemoteAddr, tcpAddr.IP.String(), privateIP)
						http.Error(w, "Forbidden", http.StatusForbidden)
						return
					}
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RegisterRequest represents the client registration request
type RegisterRequest struct {
	ID           string `json:"id"`
	WebhookURL   string `json:"webhook_url"`
	Ring         string `json:"ring"`
	SmsReceived  bool   `json:"sms_received"`
	SmsSent      bool   `json:"sms_sent"`
	SmsDelivered bool   `json:"sms_delivered"`
	SmsFailed    bool   `json:"sms_failed"`
}

// SetupAPIRouter creates the API router for external client access
func SetupAPIRouter(version string, clientManager *ClientManager, smsClient *SMSGatewayClient, allowlistManager *AllowlistManager, privateIP string) *chi.Mux {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(PrivateIPOnlyMiddleware(privateIP))

	// Allowlist routing endpoints
	r.Post("/allowlist", func(w http.ResponseWriter, r *http.Request) {
		number := r.URL.Query().Get("number")
		ring := r.URL.Query().Get("ring")
		if number == "" {
			http.Error(w, "number parameter is required", http.StatusBadRequest)
			return
		}
		if ring == "" {
			http.Error(w, "ring parameter is required", http.StatusBadRequest)
			return
		}

		// Validate ring
		if ring != "prod" && ring != "ppe" {
			http.Error(w, "ring must be 'prod' or 'ppe'", http.StatusBadRequest)
			return
		}

		// Validate phone number format
		if !phoneNumberRegex.MatchString(number) {
			http.Error(w, fmt.Sprintf("Invalid phone number: %s", number), http.StatusBadRequest)
			return
		}

		// Add to allowlist
		if err := allowlistManager.AddNumber(number, ring); err != nil {
			log.Printf("ERROR: Failed to add allowlist number %s: %v", number, err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "added", "number": number, "ring": ring})
	})

	r.Get("/allowlist", func(w http.ResponseWriter, r *http.Request) {
		numbers := allowlistManager.GetAllNumbers()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]map[string]string{"allowed_numbers": numbers})
	})

	r.Get("/allowlist/{ring}", func(w http.ResponseWriter, r *http.Request) {
		ring := chi.URLParam(r, "ring")
		numbers := allowlistManager.GetNumbersForRing(ring)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]interface{}{"ring": ring, "numbers": numbers})
	})

	r.Delete("/allowlist", func(w http.ResponseWriter, r *http.Request) {
		number := r.URL.Query().Get("number")
		if number == "" {
			http.Error(w, "number parameter is required", http.StatusBadRequest)
			return
		}

		// Remove from allowlist
		if err := allowlistManager.RemoveNumber(number); err != nil {
			log.Printf("ERROR: Failed to remove allowlist number %s: %v", number, err)
			http.Error(w, "Failed to remove number", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "removed", "number": number})
	})

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

		// Validate ring
		if req.Ring == "" {
			http.Error(w, "ring is required", http.StatusBadRequest)
			return
		}
		if req.Ring != "prod" && req.Ring != "ppe" {
			http.Error(w, "ring must be 'prod' or 'ppe'", http.StatusBadRequest)
			return
		}

		// Register the client
		client := &Client{
			ID:           req.ID,
			WebhookURL:   req.WebhookURL,
			Ring:         req.Ring,
			SmsReceived:  req.SmsReceived,
			SmsSent:      req.SmsSent,
			SmsDelivered: req.SmsDelivered,
			SmsFailed:    req.SmsFailed,
		}

		clientManager.Register(req.ID, client)

		log.Printf("Registering client %s", client.WebhookURL)

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

	return r
}

// SetupWebhookRouter creates the webhook router for SMS Gateway callbacks
func SetupWebhookRouter(clientManager *ClientManager, allowlistManager *AllowlistManager, messageCache *MessageCache) *chi.Mux {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Webhook endpoints only
	r.Post("/webhook/received", CreateWebhookHandler("received", clientManager, allowlistManager, messageCache))
	r.Post("/webhook/sent", CreateWebhookHandler("sent", clientManager, allowlistManager, messageCache))
	r.Post("/webhook/delivered", CreateWebhookHandler("delivered", clientManager, allowlistManager, messageCache))
	r.Post("/webhook/failed", CreateWebhookHandler("failed", clientManager, allowlistManager, messageCache))

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
func SetupWebhooks(client *SMSGatewayClient, webhookPort string) error {
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
		callbackURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", webhookPort, eventPath)
		if err := client.RegisterWebhook(event, callbackURL); err != nil {
			return fmt.Errorf("failed to register webhook for %s: %v", event, err)
		}
	}

	log.Printf("Webhook registration complete")
	return nil
}

// RepairWebhooks checks if our webhooks are registered and repairs them if needed
func RepairWebhooks(client *SMSGatewayClient, webhookPort string) error {
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
		expectedURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", webhookPort, eventPath)
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
			callbackURL := fmt.Sprintf("http://127.0.0.1:%s/webhook/%s", webhookPort, eventPath)
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
