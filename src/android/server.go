package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

// SetupRouter creates and configures the HTTP router
func SetupRouter(version string) *chi.Mux {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Health endpoint
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"status":"healthy","version":"%s","timestamp":"%s"}`, version, time.Now().Format(time.RFC3339))
	})
	
	// Webhook endpoints
	r.Post("/webhook/sms:received", CreateWebhookHandler("sms:received"))
	r.Post("/webhook/sms:sent", CreateWebhookHandler("sms:sent"))
	r.Post("/webhook/sms:delivered", CreateWebhookHandler("sms:delivered"))
	r.Post("/webhook/sms:failed", CreateWebhookHandler("sms:failed"))

	return r
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