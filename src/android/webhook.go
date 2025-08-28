package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"sync"
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

// MessageCache provides deduplication for webhook messages
type MessageCache struct {
	seen map[string]time.Time // MessageID -> first seen time
	mu   sync.RWMutex
}

// NewMessageCache creates a new message cache
func NewMessageCache() *MessageCache {
	return &MessageCache{
		seen: make(map[string]time.Time),
	}
}

// IsSeenAndMark checks if a message has been seen before, and marks it as seen
func (mc *MessageCache) IsSeenAndMark(messageID string) bool {
	mc.mu.Lock()
	defer mc.mu.Unlock()
	
	if _, exists := mc.seen[messageID]; exists {
		return true
	}
	
	mc.seen[messageID] = time.Now()
	return false
}

// Cleanup removes entries older than the given duration
func (mc *MessageCache) Cleanup(ttl time.Duration) {
	mc.mu.Lock()
	defer mc.mu.Unlock()
	
	cutoff := time.Now().Add(-ttl)
	for messageID, timestamp := range mc.seen {
		if timestamp.Before(cutoff) {
			delete(mc.seen, messageID)
		}
	}
}

// CreateWebhookHandler creates a handler for webhook endpoints
func CreateWebhookHandler(eventType string, clientManager *ClientManager, allowlistManager *AllowlistManager, messageCache *MessageCache) http.HandlerFunc {
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
		
		// Extract MessageID for deduplication (all SMS events have MessageID)
		var messageID string
		var phoneNumber string
		switch eventType {
		case "received":
			var payload SmsReceivedPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			messageID = payload.MessageID
			phoneNumber = payload.PhoneNumber
			log.Printf("Webhook %s: From=%s, Message='%s', ReceivedAt=%s, MessageID=%s", 
				eventType, payload.PhoneNumber, payload.Message, payload.ReceivedAt, payload.MessageID)
			
		case "sent":
			var payload SmsSentPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			messageID = payload.MessageID
			phoneNumber = payload.PhoneNumber
			log.Printf("Webhook %s: To=%s, SentAt=%s, MessageID=%s", 
				eventType, payload.PhoneNumber, payload.SentAt, payload.MessageID)
			
		case "delivered":
			var payload SmsDeliveredPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			messageID = payload.MessageID
			phoneNumber = payload.PhoneNumber
			log.Printf("Webhook %s: To=%s, DeliveredAt=%s, MessageID=%s", 
				eventType, payload.PhoneNumber, payload.DeliveredAt, payload.MessageID)
			
		case "failed":
			var payload SmsFailedPayload
			if err := json.Unmarshal(payloadJSON, &payload); err != nil {
				log.Printf("ERROR: Failed to parse %s payload: %v", eventType, err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			messageID = payload.MessageID
			phoneNumber = payload.PhoneNumber
			log.Printf("Webhook %s: To=%s, FailedAt=%s, Reason='%s', MessageID=%s", 
				eventType, payload.PhoneNumber, payload.FailedAt, payload.Reason, payload.MessageID)
			
		default:
			log.Printf("Webhook %s: Unknown event type - raw payload: %s", eventType, string(payloadJSON))
		}
		
		// Check for duplicate messages (SMS Gateway bug workaround)
		// Use eventType-messageID as key since same messageID is used across sent/delivered/failed events
		if messageID != "" {
			dedupKey := eventType + "-" + messageID
			if messageCache.IsSeenAndMark(dedupKey) {
				log.Printf("Webhook %s: DUPLICATE detected for MessageID=%s, ignoring", eventType, messageID)
				// Return 200 OK immediately to SMS Gateway
				w.WriteHeader(http.StatusOK)
				w.Write([]byte("OK"))
				return
			}
		}
		
		// Return 200 OK immediately to SMS Gateway
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
		
		// Get all clients and filter by event subscription
		clients := clientManager.List()
		filtered := FilterByEvent(clients, eventType)
		
		// Check if phone number is in allowlist
		targetRing := allowlistManager.GetRing(phoneNumber)
		if targetRing == "" {
			// Number not in allowlist, don't route to anyone
			log.Printf("Phone number %s not in allowlist, ignoring webhook %s", phoneNumber, eventType)
			return
		}
		
		// Filter clients by target ring
		var ringFiltered []*Client
		for _, client := range filtered {
			if client.Ring == targetRing {
				ringFiltered = append(ringFiltered, client)
			}
		}
		filtered = ringFiltered
		
		// Forward to filtered clients synchronously
		forwardToClients(filtered, eventType, body)
	}
}

// FilterByEvent returns clients that subscribe to the given event type
func FilterByEvent(clients []*Client, eventType string) []*Client {
	var filtered []*Client
	for _, client := range clients {
		var subscribed bool
		switch eventType {
		case "received":
			subscribed = client.SmsReceived
		case "sent":
			subscribed = client.SmsSent
		case "delivered":
			subscribed = client.SmsDelivered
		case "failed":
			subscribed = client.SmsFailed
		}
		if subscribed {
			filtered = append(filtered, client)
		}
	}
	return filtered
}


// forwardToClients forwards the webhook to the given clients
func forwardToClients(clients []*Client, eventType string, body []byte) {
	var wg sync.WaitGroup
	
	for _, client := range clients {
		wg.Add(1)
		go func(client *Client) {
			defer wg.Done()
			
			// Append event type to webhook URL
			webhookURL := client.WebhookURL + "/" + eventType
			
			// Try forwarding with up to 3 attempts
			maxAttempts := 3
			for attempt := 1; attempt <= maxAttempts; attempt++ {
				resp, err := http.Post(webhookURL, "application/json", bytes.NewBuffer(body))
				if err != nil {
					log.Printf("ERROR: Failed to forward to client %s at %s (attempt %d/%d): %v", 
						client.ID, webhookURL, attempt, maxAttempts, err)
					if attempt < maxAttempts {
						time.Sleep(time.Second)
					}
				} else {
					defer resp.Body.Close()
					
					if resp.StatusCode >= 200 && resp.StatusCode < 300 {
						log.Printf("Forwarded %s to client %s at %s (status %d, attempt %d/%d)", 
							eventType, client.ID, webhookURL, resp.StatusCode, attempt, maxAttempts)
						break // Success, stop retrying
					} else {
						log.Printf("ERROR: Client %s returned status %d from %s (attempt %d/%d)", 
							client.ID, resp.StatusCode, webhookURL, attempt, maxAttempts)
						if attempt < maxAttempts {
							time.Sleep(time.Second)
						}
					}
				}
			}
		}(client)
	}
	
	// Wait for all forwards to complete
	wg.Wait()
}
