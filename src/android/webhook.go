package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"time"
)

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

// CreateWebhookHandler creates a handler for webhook endpoints
func CreateWebhookHandler(eventType string, clientManager *ClientManager) http.HandlerFunc {
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
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			log.Printf("Webhook %s: From=%s, Message='%s', ReceivedAt=%s, MessageID=%s", 
				eventType, payload.PhoneNumber, payload.Message, payload.ReceivedAt, payload.MessageID)
			
		case "sms:sent":
			var payload SmsSentPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			log.Printf("Webhook %s: To=%s, SentAt=%s, MessageID=%s", 
				eventType, payload.PhoneNumber, payload.SentAt, payload.MessageID)
			
		case "sms:delivered":
			var payload SmsDeliveredPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			log.Printf("Webhook %s: To=%s, DeliveredAt=%s, MessageID=%s", 
				eventType, payload.PhoneNumber, payload.DeliveredAt, payload.MessageID)
			
		case "sms:failed":
			var payload SmsFailedPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			log.Printf("Webhook %s: To=%s, FailedAt=%s, Reason='%s', MessageID=%s", 
				eventType, payload.PhoneNumber, payload.FailedAt, payload.Reason, payload.MessageID)
			
		default:
			log.Printf("Webhook %s: Unknown event type - raw payload: %s", eventType, string(payloadJSON))
		}
		
		// Return 200 OK immediately to SMS Gateway
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
		
		// Forward to registered clients synchronously
		forwardToClients(eventType, body, clientManager)
	}
}

// forwardToClients forwards the webhook to all registered clients that subscribe to this event
func forwardToClients(eventType string, body []byte, clientManager *ClientManager) {
	clients := clientManager.List()
	
	for id, client := range clients {
		// Check if client subscribes to this event type
		shouldForward := false
		switch eventType {
		case "sms:received":
			shouldForward = client.SmsReceived
		case "sms:sent":
			shouldForward = client.SmsSent
		case "sms:delivered":
			shouldForward = client.SmsDelivered
		case "sms:failed":
			shouldForward = client.SmsFailed
		}
		
		if shouldForward {
			// Try forwarding with up to 3 attempts
			maxAttempts := 3
			for attempt := 1; attempt <= maxAttempts; attempt++ {
				resp, err := http.Post(client.WebhookURL, "application/json", bytes.NewBuffer(body))
				if err != nil {
					log.Printf("ERROR: Failed to forward %s to client %s (attempt %d/%d): %v", 
						eventType, id, attempt, maxAttempts, err)
					if attempt < maxAttempts {
						time.Sleep(time.Second)
					}
				} else {
					defer resp.Body.Close()
					
					if resp.StatusCode >= 200 && resp.StatusCode < 300 {
						log.Printf("Forwarded %s to client %s (status %d, attempt %d/%d)", 
							eventType, id, resp.StatusCode, attempt, maxAttempts)
						break // Success, stop retrying
					} else {
						log.Printf("ERROR: Client %s returned status %d for %s (attempt %d/%d)", 
							id, resp.StatusCode, eventType, attempt, maxAttempts)
						if attempt < maxAttempts {
							time.Sleep(time.Second)
						}
					}
				}
			}
		}
	}
}