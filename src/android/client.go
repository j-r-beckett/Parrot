package main

import (
	"sync"
	"time"
)

// Client represents a registered webhook client
type Client struct {
	WebhookURL   string    `json:"webhook_url"`
	RegisteredAt time.Time `json:"registered_at"`
	LastSeen     time.Time `json:"last_seen"`
	SmsReceived  bool      `json:"sms_received"`
	SmsSent      bool      `json:"sms_sent"`
	SmsDelivered bool      `json:"sms_delivered"`
	SmsFailed    bool      `json:"sms_failed"`
}

// ClientManager manages registered clients with thread-safe operations
type ClientManager struct {
	clients  map[string]*Client
	mu       sync.Mutex
	stopChan chan struct{}
	wg       sync.WaitGroup
}

// NewClientManager creates a new client manager
func NewClientManager() *ClientManager {
	return &ClientManager{
		clients:  make(map[string]*Client),
		stopChan: make(chan struct{}),
	}
}

// Register adds or updates a client
func (cm *ClientManager) Register(id string, client *Client) {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	
	client.LastSeen = time.Now()
	if existing, exists := cm.clients[id]; exists {
		// Preserve registration time on updates
		client.RegisteredAt = existing.RegisteredAt
	} else {
		client.RegisteredAt = time.Now()
	}
	
	cm.clients[id] = client
}

// Get retrieves a client by ID
func (cm *ClientManager) Get(id string) (*Client, bool) {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	
	client, exists := cm.clients[id]
	return client, exists
}

// List returns all active clients
func (cm *ClientManager) List() map[string]*Client {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	
	// Return a copy to avoid race conditions
	result := make(map[string]*Client)
	for id, client := range cm.clients {
		result[id] = client
	}
	return result
}

// StartPruning begins the background pruning goroutine
func (cm *ClientManager) StartPruning() {
	cm.wg.Add(1)
	go func() {
		defer cm.wg.Done()
		
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		
		for {
			select {
			case <-ticker.C:
				cm.prune()
			case <-cm.stopChan:
				return
			}
		}
	}()
}

// prune removes clients that haven't been seen in 60 seconds
func (cm *ClientManager) prune() {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	
	cutoff := time.Now().Add(-60 * time.Second)
	for id, client := range cm.clients {
		if client.LastSeen.Before(cutoff) {
			delete(cm.clients, id)
		}
	}
}

// Stop gracefully shuts down the client manager
func (cm *ClientManager) Stop() {
	close(cm.stopChan)
	cm.wg.Wait()
}