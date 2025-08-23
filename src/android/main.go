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
	version          = "0.4"
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

// WebhookEvent represents the top-level webhook event structure
type WebhookEvent struct {
	ID        string      `json:"id"`
	WebhookID string      `json:"webhookId"`
	DeviceID  string      `json:"deviceId"`
	Event     string      `json:"event"`
	Payload   interface{} `json:"payload"`
}

// SmsEventPayload is the base payload for SMS-related events
type SmsEventPayload struct {
	MessageID   string  `json:"messageId"`
	PhoneNumber string  `json:"phoneNumber"`
	SimNumber   *int    `json:"simNumber"`
}

// SmsReceivedPayload for sms:received events
type SmsReceivedPayload struct {
	SmsEventPayload
	Message    string `json:"message"`
	ReceivedAt string `json:"receivedAt"`
}

// SmsSentPayload for sms:sent events
type SmsSentPayload struct {
	SmsEventPayload
	SentAt string `json:"sentAt"`
}

// SmsDeliveredPayload for sms:delivered events
type SmsDeliveredPayload struct {
	SmsEventPayload
	DeliveredAt string `json:"deliveredAt"`
}

// SmsFailedPayload for sms:failed events
type SmsFailedPayload struct {
	SmsEventPayload
	FailedAt string `json:"failedAt"`
	Reason   string `json:"reason"`
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
	
	// Register all webhook types (Phase 1.4a)
	webhookEvents := []string{"sms:received", "sms:sent", "sms:delivered", "sms:failed"}
	for _, event := range webhookEvents {
		log.Printf("Registering webhook for %s", event)
		if err := client.RegisterWebhook(event); err != nil {
			return fmt.Errorf("failed to register webhook for %s: %v", event, err)
		}
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
	
	// Webhook endpoints - parse and log structured data
	webhookHandler := func(eventType string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			body, err := io.ReadAll(r.Body)
			if err != nil {
				log.Printf("ERROR: Failed to read webhook body for %s: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			
			// Parse the webhook event
			var event WebhookEvent
			if err := json.Unmarshal(body, &event); err != nil {
				log.Printf("ERROR: Failed to parse webhook %s: %v - body: %s", eventType, err, string(body))
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			
			// Parse the specific payload based on event type
			payloadJSON, _ := json.Marshal(event.Payload)
			
			switch eventType {
			case "sms:received":
				var payload SmsReceivedPayload
				if err := json.Unmarshal(payloadJSON, &payload); err != nil {
					log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				} else {
					log.Printf("Webhook %s: From=%s, Message='%s', ReceivedAt=%s, MessageID=%s", 
						eventType, payload.PhoneNumber, payload.Message, payload.ReceivedAt, payload.MessageID)
				}
				
			case "sms:sent":
				var payload SmsSentPayload
				if err := json.Unmarshal(payloadJSON, &payload); err != nil {
					log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				} else {
					log.Printf("Webhook %s: To=%s, SentAt=%s, MessageID=%s", 
						eventType, payload.PhoneNumber, payload.SentAt, payload.MessageID)
				}
				
			case "sms:delivered":
				var payload SmsDeliveredPayload
				if err := json.Unmarshal(payloadJSON, &payload); err != nil {
					log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				} else {
					log.Printf("Webhook %s: To=%s, DeliveredAt=%s, MessageID=%s", 
						eventType, payload.PhoneNumber, payload.DeliveredAt, payload.MessageID)
				}
				
			case "sms:failed":
				var payload SmsFailedPayload
				if err := json.Unmarshal(payloadJSON, &payload); err != nil {
					log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				} else {
					log.Printf("Webhook %s: To=%s, FailedAt=%s, Reason='%s', MessageID=%s", 
						eventType, payload.PhoneNumber, payload.FailedAt, payload.Reason, payload.MessageID)
				}
				
			default:
				log.Printf("Webhook %s: Unknown event type - raw payload: %s", eventType, string(payloadJSON))
			}
			
			// Return 200 OK immediately
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("OK"))
		}
	}
	
	r.Post("/webhook/sms:received", webhookHandler("sms:received"))
	r.Post("/webhook/sms:sent", webhookHandler("sms:sent"))
	r.Post("/webhook/sms:delivered", webhookHandler("sms:delivered"))
	r.Post("/webhook/sms:failed", webhookHandler("sms:failed"))

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