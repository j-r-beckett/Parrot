package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// Test health endpoint
func TestHealthEndpoint(t *testing.T) {
	// Create router with test version
	cm := NewClientManager()
	router := SetupRouter("test-version", cm)
	
	// Create test server
	ts := httptest.NewServer(router)
	defer ts.Close()
	
	// Make request
	resp, err := http.Get(ts.URL + "/health")
	if err != nil {
		t.Fatalf("Failed to make request: %v", err)
	}
	defer resp.Body.Close()
	
	// Check status code
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}
	
	// Check content type
	contentType := resp.Header.Get("Content-Type")
	if contentType != "application/json" {
		t.Errorf("Expected Content-Type 'application/json', got '%s'", contentType)
	}
	
	// Parse response
	var result map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}
	
	// Check required fields
	if result["status"] != "healthy" {
		t.Errorf("Expected status 'healthy', got '%s'", result["status"])
	}
	
	if result["version"] != "test-version" {
		t.Errorf("Expected version 'test-version', got '%s'", result["version"])
	}
	
	if result["timestamp"] == "" {
		t.Error("Timestamp should not be empty")
	}
	
	// Validate timestamp format
	if _, err := time.Parse(time.RFC3339, result["timestamp"]); err != nil {
		t.Errorf("Invalid timestamp format: %v", err)
	}
}

// Test that all webhook endpoints are registered
func TestWebhookEndpointsRegistered(t *testing.T) {
	cm := NewClientManager()
	router := SetupRouter("test", cm)
	ts := httptest.NewServer(router)
	defer ts.Close()
	
	events := []string{"sms:received", "sms:sent", "sms:delivered", "sms:failed"}
	
	for _, event := range events {
		// Send empty JSON object (will fail parsing but that's ok for this test)
		resp, err := http.Post(ts.URL+"/webhook/"+event, "application/json", bytes.NewBufferString("{}"))
		if err != nil {
			t.Fatalf("Failed to make request to %s: %v", event, err)
		}
		resp.Body.Close()
		
		// Should not be 404 (endpoint exists)
		if resp.StatusCode == http.StatusNotFound {
			t.Errorf("Webhook endpoint /webhook/%s not registered", event)
		}
	}
}