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
		
		// Variable to hold phone number for filtering
		var phoneNumber string
		
		switch eventType {
		case "sms:received":
			var payload SmsReceivedPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			phoneNumber = payload.PhoneNumber
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
		
		// Get all clients and filter by event subscription
		clients := clientManager.List()
		filtered := FilterByEvent(clients, eventType)
		
		// For sms:received, also filter by phone number
		if eventType == "sms:received" {
			filtered = FilterByNumberIncludes(filtered, phoneNumber)
			filtered = FilterByNumberExcludes(filtered, phoneNumber)
		}
		
		// Forward to filtered clients synchronously
		forwardToClients(filtered, body)
	}
}

// FilterByEvent returns clients that subscribe to the given event type
func FilterByEvent(clients []*Client, eventType string) []*Client {
	var filtered []*Client
	for _, client := range clients {
		var subscribed bool
		switch eventType {
		case "sms:received":
			subscribed = client.SmsReceived
		case "sms:sent":
			subscribed = client.SmsSent
		case "sms:delivered":
			subscribed = client.SmsDelivered
		case "sms:failed":
			subscribed = client.SmsFailed
		}
		if subscribed {
			filtered = append(filtered, client)
		}
	}
	return filtered
}

// FilterByNumberIncludes returns clients that include the phone number (or have no include list)
func FilterByNumberIncludes(clients []*Client, phoneNumber string) []*Client {
	var filtered []*Client
	for _, client := range clients {
		var subscribed bool = len(client.IncludeReceivedFrom) == 0
		// Check if number is in include list
		for _, num := range client.IncludeReceivedFrom {
			if num == phoneNumber {
				subscribed = true
				break
			}
		}
		
		if subscribed {
			filtered = append(filtered, client)
		}
	}
	return filtered
}

// FilterByNumberExcludes returns clients that don't exclude the phone number
func FilterByNumberExcludes(clients []*Client, phoneNumber string) []*Client {
	var filtered []*Client
	for _, client := range clients {
		var subscribed bool = true
		// Check if number is in exclude list
		for _, num := range client.ExcludeReceivedFrom {
			if num == phoneNumber {
				subscribed = false
				break
			}
		}
		
		if subscribed {
			filtered = append(filtered, client)
		}
	}
	return filtered
}

// forwardToClients forwards the webhook to the given clients
func forwardToClients(clients []*Client, body []byte) {
	for _, client := range clients {
		// Try forwarding with up to 3 attempts
		maxAttempts := 3
		for attempt := 1; attempt <= maxAttempts; attempt++ {
			resp, err := http.Post(client.WebhookURL, "application/json", bytes.NewBuffer(body))
			if err != nil {
				log.Printf("ERROR: Failed to forward to client %s (attempt %d/%d): %v", 
					client.ID, attempt, maxAttempts, err)
				if attempt < maxAttempts {
					time.Sleep(time.Second)
				}
			} else {
				defer resp.Body.Close()
				
				if resp.StatusCode >= 200 && resp.StatusCode < 300 {
					log.Printf("Forwarded to client %s (status %d, attempt %d/%d)", 
						client.ID, resp.StatusCode, attempt, maxAttempts)
					break // Success, stop retrying
				} else {
					log.Printf("ERROR: Client %s returned status %d (attempt %d/%d)", 
						client.ID, resp.StatusCode, attempt, maxAttempts)
					if attempt < maxAttempts {
						time.Sleep(time.Second)
					}
				}
			}
		}
	}
}
