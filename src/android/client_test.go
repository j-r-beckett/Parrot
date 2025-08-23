package main

import (
	"testing"
	"time"
)

func TestClientManager(t *testing.T) {
	cm := NewClientManager()
	
	// Test registration
	client1 := &Client{
		WebhookURL:   "http://example.com/webhook",
		SmsReceived:  true,
		SmsSent:      false,
		SmsDelivered: true,
		SmsFailed:    false,
	}
	
	cm.Register("test1", client1)
	
	// Test Get
	retrieved, exists := cm.Get("test1")
	if !exists {
		t.Error("Expected client to exist after registration")
	}
	if retrieved.WebhookURL != client1.WebhookURL {
		t.Errorf("Expected webhook URL %s, got %s", client1.WebhookURL, retrieved.WebhookURL)
	}
	
	// Test List
	clients := cm.List()
	if len(clients) != 1 {
		t.Errorf("Expected 1 client, got %d", len(clients))
	}
	
	// Test update preserves registration time
	time.Sleep(10 * time.Millisecond)
	originalRegTime := retrieved.RegisteredAt
	
	client1Updated := &Client{
		WebhookURL: "http://updated.com/webhook",
	}
	cm.Register("test1", client1Updated)
	
	retrieved2, _ := cm.Get("test1")
	if !retrieved2.RegisteredAt.Equal(originalRegTime) {
		t.Error("Registration time should be preserved on update")
	}
	if retrieved2.WebhookURL != "http://updated.com/webhook" {
		t.Error("Webhook URL should be updated")
	}
}

func TestClientPruning(t *testing.T) {
	cm := NewClientManager()
	
	// Register a client
	client := &Client{
		WebhookURL: "http://example.com/webhook",
	}
	cm.Register("test1", client)
	
	// Manually set LastSeen to old time
	cm.mu.Lock()
	cm.clients["test1"].LastSeen = time.Now().Add(-61 * time.Second)
	cm.mu.Unlock()
	
	// Run prune
	cm.prune()
	
	// Client should be removed
	_, exists := cm.Get("test1")
	if exists {
		t.Error("Expected old client to be pruned")
	}
	
	// Register a fresh client
	cm.Register("test2", client)
	
	// Run prune
	cm.prune()
	
	// Fresh client should still exist
	_, exists = cm.Get("test2")
	if !exists {
		t.Error("Expected fresh client to remain after pruning")
	}
}

func TestClientManagerLifecycle(t *testing.T) {
	cm := NewClientManager()
	
	// Start pruning
	cm.StartPruning()
	
	// Register a client
	client := &Client{
		WebhookURL: "http://example.com/webhook",
	}
	cm.Register("test1", client)
	
	// Stop should complete without hanging
	done := make(chan bool)
	go func() {
		cm.Stop()
		done <- true
	}()
	
	select {
	case <-done:
		// Success
	case <-time.After(1 * time.Second):
		t.Error("Stop() took too long, possible deadlock")
	}
}